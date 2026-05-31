"""Deterministic controller for the structured assistant pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from backend.assistants import (
    run_app_ui_assistant,
    run_ba_assistant,
    run_critic_assistant,
    run_dev_assistant,
    run_test_assistant,
)
from backend.handoff.handoff_builder import build_handoff
from backend.handoff.storage import latest_handoff, load_handoff, save_handoff
from backend.orchestrator.approval_gate import (
    approve_stage as apply_approval,
    can_run_stage,
    skip_stage as apply_skip,
)
from backend.orchestrator.pipeline_state import PipelineState, StageFeedback, StageState, create_initial_pipeline_state, utc_now
from backend.repo_context.storage import read_json, write_json
from backend.workflow.pipeline_templates import list_stage_names, stage_metadata_map
from backend.workflow.stage_registry import run_stage_critic, run_stage_output
from backend.workflow.workflow_router import route_work_item_to_template


class PipelineController:
    """JSON-backed pipeline orchestration with explicit stage progression."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("AI_GEN_PIPELINE_ROOT", ".ai_gen_pipelines"))
        self.root.mkdir(parents=True, exist_ok=True)

    def create_pipeline(
        self,
        work_item: dict,
        source: str = "azure_devops",
        repo_context: dict | None = None,
        refinement: dict | None = None,
    ) -> dict:
        pipeline_id = f"pipeline_{uuid4().hex[:12]}"
        work_item_id = str(work_item.get("id") or work_item.get("work_item_id") or uuid4().hex[:8])
        classification, template = route_work_item_to_template(work_item, refinement=refinement)
        state = create_initial_pipeline_state(
            pipeline_id=pipeline_id,
            source=source,
            work_item_id=work_item_id,
            work_item=work_item,
            repo_context=repo_context,
            refinement=refinement,
            workflow_template=template["name"],
            stage_order=list_stage_names(template),
            stage_metadata=stage_metadata_map(template),
            work_item_classification=classification,
        )
        self.save_pipeline(state)
        return self._serialize_pipeline(state)

    def get_pipeline(self, pipeline_id: str) -> dict:
        state = self.load_pipeline(pipeline_id)
        return self._serialize_pipeline(state)

    def get_pipeline_for_work_item(self, work_item_id: str | int) -> dict | None:
        state = self.load_latest_pipeline_for_work_item(work_item_id)
        return self._serialize_pipeline(state) if state else None

    def run_stage(self, pipeline_id: str, stage: str, regenerate: bool = False) -> dict:
        state = self.load_pipeline(pipeline_id)
        allowed, reason = can_run_stage(state, stage, regenerate=regenerate)
        if not allowed:
            raise ValueError(reason)
        stage_state = state.stages[stage]
        stage_state.version = stage_state.version + 1 if regenerate or stage_state.version else 1
        review_context = self._build_review_context(stage_state) if regenerate else None
        output = self._run_stage_output(state, stage, review_context=review_context)
        critic = self._run_critic_for_stage(stage, output, state)
        unresolved, resolved = self._split_findings(stage_state, critic)
        stage_state.output = output
        stage_state.critic = critic
        stage_state.status = "needs_revision" if critic.get("decision") == "needs_revision" else "generated"
        stage_state.approved = False
        stage_state.approved_at = None
        stage_state.approved_by = None
        stage_state.unresolved_findings = unresolved
        stage_state.resolved_findings = resolved
        handoff = build_handoff(
            pipeline_state=state,
            stage=stage,
            stage_output=output,
            refinement=state.refinement,
            repo_context=state.repo_context,
            status="draft",
        )
        save_handoff(handoff)
        stage_state.handoff_id = handoff["handoff_id"]
        state.current_stage = stage
        self._touch_pipeline(state)
        self.save_pipeline(state)
        return self._serialize_pipeline(state)

    def approve_stage(self, pipeline_id: str, stage: str, approved_by: str | None = None) -> dict:
        state = self.load_pipeline(pipeline_id)
        state = apply_approval(state, stage, approved_by=approved_by)
        stage_state = state.stages[stage]
        handoff = build_handoff(
            pipeline_state=state,
            stage=stage,
            stage_output=stage_state.output,
            refinement=state.refinement,
            repo_context=state.repo_context,
            status="approved",
        )
        save_handoff(handoff)
        stage_state.handoff_id = handoff["handoff_id"]
        self._touch_pipeline(state)
        self.save_pipeline(state)
        return self._serialize_pipeline(state)

    def skip_stage(self, pipeline_id: str, stage: str, reason: str) -> dict:
        state = self.load_pipeline(pipeline_id)
        state = apply_skip(state, stage, reason=reason)
        self._touch_pipeline(state)
        self.save_pipeline(state)
        return self._serialize_pipeline(state)

    def add_stage_feedback(self, pipeline_id: str, stage: str, comment: str, author: str | None = None) -> dict:
        state = self.load_pipeline(pipeline_id)
        stage_state = state.stages.get(stage)
        if stage_state is None:
            raise ValueError(f"Unknown stage: {stage}")
        normalized = str(comment).strip()
        if not normalized:
            raise ValueError("Feedback comment is required.")
        feedback = StageFeedback(
            id=f"feedback_{uuid4().hex[:12]}",
            author=(author or "reviewer").strip() or "reviewer",
            timestamp=utc_now(),
            comment=normalized,
        )
        stage_state.review_feedback.append(feedback)
        self._touch_pipeline(state)
        self.save_pipeline(state)
        return self._serialize_pipeline(state)

    def load_pipeline(self, pipeline_id: str) -> PipelineState:
        data = read_json(self.root / f"{pipeline_id}.json", default=None)
        if not data:
            raise ValueError(f"Unknown pipeline: {pipeline_id}")
        return PipelineState.from_dict(data)

    def save_pipeline(self, state: PipelineState) -> None:
        write_json(self.root / f"{state.pipeline_id}.json", state.to_dict())

    def latest_handoff(self, work_item_id: str | int, stage: str, status: str | None = None) -> dict | None:
        return latest_handoff(work_item_id, stage, status=status)

    def load_handoff(self, handoff_id: str) -> dict | None:
        return load_handoff(handoff_id)

    def load_latest_pipeline_for_work_item(self, work_item_id: str | int) -> PipelineState | None:
        target = str(work_item_id)
        latest_state: PipelineState | None = None
        for path in sorted(self.root.glob("pipeline_*.json")):
            data = read_json(path, default=None)
            if not data or str(data.get("work_item_id", "")) != target:
                continue
            state = PipelineState.from_dict(data)
            if latest_state is None or state.updated_at > latest_state.updated_at:
                latest_state = state
        return latest_state

    def _run_stage_output(self, state: PipelineState, stage: str, review_context: dict | None = None) -> dict:
        return run_stage_output(
            stage,
            state,
            approved_stage_context=lambda stage_name: self._approved_stage_context(state, stage_name),
            review_context=review_context,
        )

    def _run_critic_for_stage(self, stage: str, output: dict, state: PipelineState) -> dict:
        return run_stage_critic(
            stage,
            output,
            state,
            approved_stage_context=lambda stage_name: self._approved_stage_context(state, stage_name),
        )

    def _touch_pipeline(self, state: PipelineState) -> None:
        state.version += 1
        state.updated_at = utc_now()

    def _build_review_context(self, stage_state: StageState) -> dict:
        return {
            "previous_output": stage_state.output or {},
            "critic_findings": [finding for finding in stage_state.unresolved_findings if finding.get("status", "open") == "open"],
            "review_feedback": [feedback.to_dict() for feedback in stage_state.review_feedback],
        }

    def _split_findings(self, stage_state: StageState, critic: dict) -> tuple[list[dict], list[dict]]:
        current = []
        for finding in critic.get("findings", []):
            item = dict(finding)
            item.setdefault("target_stage", stage_state.stage)
            item.setdefault("source_stage", stage_state.stage)
            item["status"] = "open"
            current.append(item)
        current_ids = {finding.get("id") for finding in current}
        resolved = [dict(finding) for finding in stage_state.resolved_findings]
        for previous in stage_state.unresolved_findings:
            if previous.get("id") not in current_ids:
                item = dict(previous)
                item["status"] = "resolved"
                resolved.append(item)
        return current, _dedupe_findings(resolved)

    def _serialize_pipeline(self, state: PipelineState) -> dict:
        data = state.to_dict()
        data["allowed_actions"] = self._allowed_actions(state)
        data["current_stage"] = self._active_stage_name(state)
        data["current_stage_findings"] = self._current_stage_findings(state)
        data["current_stage_blocking_findings"] = self._current_stage_blocking_findings(state)
        data["all_findings"] = self._all_findings(state)
        data["resolved_findings"] = self._resolved_findings(state)
        print(
            "ai-gen pipeline"
            f" current_stage={data['current_stage']}"
            f" current_stage_findings={len(data['current_stage_findings'])}"
            f" current_stage_blocking_findings={len(data['current_stage_blocking_findings'])}"
            f" all_findings={len(data['all_findings'])}"
            f" resolved_findings={len(data['resolved_findings'])}"
        )
        return data

    def _allowed_actions(self, state: PipelineState) -> dict[str, list[str]]:
        current_stage = self._active_stage_name(state)
        actions = {
            "generate_stages": [],
            "regenerate_stages": [],
            "approve_stages": [],
            "skip_stages": [],
            "view_handoff_stages": [],
            "feedback_stages": [],
            "current_stage_actions": [],
        }
        for stage_name, stage_state in state.stages.items():
            if stage_state.status == "pending" and not stage_state.approved:
                actions["generate_stages"].append(stage_name)
            if stage_state.status == "generated" and not stage_state.approved:
                actions["regenerate_stages"].append(stage_name)
            has_blocking_findings = any(
                finding.get("severity") == "blocking" and finding.get("status", "open") == "open"
                for finding in stage_state.unresolved_findings
            )
            if (
                bool(stage_state.output)
                and stage_state.status == "generated"
                and not stage_state.approved
                and not has_blocking_findings
            ):
                actions["approve_stages"].append(stage_name)
            if self._is_optional_stage(state, stage_name) and stage_state.status in {"pending", "generated"} and not stage_state.approved:
                actions["skip_stages"].append(stage_name)
            if stage_state.handoff_id:
                actions["view_handoff_stages"].append(stage_name)
            if stage_state.status == "needs_revision":
                actions["feedback_stages"].append(stage_name)
            if stage_name == current_stage:
                actions["current_stage_actions"] = self._current_stage_actions(stage_name, stage_state, has_blocking_findings)
        return actions

    def _current_stage_actions(self, stage_name: str, stage_state: StageState, has_blocking_findings: bool) -> list[str]:
        actions: list[str] = []
        status = stage_state.status
        if status == "pending" and not stage_state.approved:
            actions.append("generate")
            if self._is_optional_stage_name(stage_name):
                actions.append("skip_stage")
        elif status == "generated" and not stage_state.approved:
            actions.append("regenerate")
            if stage_state.handoff_id:
                actions.append("view_handoff")
            if not has_blocking_findings:
                actions.append("approve")
            if self._is_optional_stage_name(stage_name):
                actions.append("skip_stage")
        elif status == "needs_revision" and not stage_state.approved:
            actions.extend(["add_clarification", "regenerate_with_clarifications"])
            if stage_state.handoff_id:
                actions.append("view_handoff")
        elif status == "approved":
            if stage_state.handoff_id:
                actions.extend(["view_handoff", "copy_handoff"])
        return actions

    def _approved_stage_context(self, state: PipelineState, stage: str) -> dict:
        stage_state = state.stages.get(stage)
        output = dict(stage_state.output) if stage_state and stage_state.output else {}
        if stage_state and stage_state.approved:
            output["unknowns"] = []
        return output

    def _current_stage_findings(self, state: PipelineState) -> list[dict]:
        stage_name = self._active_stage_name(state)
        stage_state = state.stages.get(stage_name)
        if not stage_state:
            return []
        return [
            dict(finding)
            for finding in stage_state.unresolved_findings
            if finding.get("status", "open") == "open"
            and finding.get("target_stage", stage_name) == stage_name
        ]

    def _current_stage_blocking_findings(self, state: PipelineState) -> list[dict]:
        return [
            finding
            for finding in self._current_stage_findings(state)
            if finding.get("severity") == "blocking"
        ]

    def _all_findings(self, state: PipelineState) -> list[dict]:
        findings: list[dict] = []
        for stage_name in state.stages:
            stage_state = state.stages[stage_name]
            for finding in stage_state.unresolved_findings + stage_state.resolved_findings:
                item = dict(finding)
                item.setdefault("target_stage", stage_name)
                item.setdefault("source_stage", stage_name)
                findings.append(item)
        return findings

    def _resolved_findings(self, state: PipelineState) -> list[dict]:
        findings: list[dict] = []
        for stage_name in state.stages:
            stage_state = state.stages[stage_name]
            for finding in stage_state.resolved_findings:
                item = dict(finding)
                item.setdefault("target_stage", stage_name)
                item.setdefault("source_stage", stage_name)
                item["status"] = "resolved"
                findings.append(item)
        return findings

    def _active_stage_name(self, state: PipelineState) -> str:
        for stage_name in list(getattr(state, "stage_order", []) or []):
            stage_state = state.stages.get(stage_name)
            if not stage_state:
                continue
            if stage_state.status in {"generated", "needs_revision", "pending"}:
                return stage_name
        return state.current_stage

    def _is_optional_stage(self, state: PipelineState, stage_name: str) -> bool:
        return bool(state.stage_metadata.get(stage_name, {}).get("optional"))

    def _is_optional_stage_name(self, stage_name: str) -> bool:
        return stage_name.endswith("_optional")


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for finding in findings:
        finding_id = str(finding.get("id", "")).strip()
        if finding_id and finding_id not in seen:
            seen.add(finding_id)
            output.append(finding)
    return output
