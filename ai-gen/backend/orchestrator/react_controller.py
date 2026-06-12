"""Deterministic controller for the structured assistant pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from backend.context import build_effective_work_item_context
from backend.handoff.handoff_builder import build_handoff
from backend.handoff.storage import latest_handoff, load_handoff, save_handoff
from backend.orchestrator.approval_gate import (
    approve_stage as apply_approval,
    can_run_stage,
    skip_stage as apply_skip,
)
from backend.refinement.canonical_vocabulary import (
    normalize_field,
    normalize_flow,
    normalize_surface,
    normalize_validation,
    normalize_variant,
)
from backend.refinement.task_refiner import refine_task
from backend.orchestrator.pipeline_state import PipelineState, StageFeedback, StageState, create_initial_pipeline_state, utc_now
from backend.repo_context.storage import read_json, write_json
from backend.workflow.action_visibility import get_allowed_actions
from backend.workflow.pipeline_templates import list_stage_names, stage_metadata_map
from backend.workflow.state_machines import WorkflowSnapshot, get_state_machine
from backend.workflow.stage_registry import run_stage_critic, run_stage_output
from backend.workflow.work_item_drafts import approve_drafts, build_create_requests, flatten_drafts, mark_drafts_created, normalize_drafts
from backend.workflow.workflow_router import route_work_item_to_template
from backend.audit.trail import record_event as _audit


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
        ai_gen_comments: list[dict] | None = None,
        team_comments: list[dict] | None = None,
        epic_context: dict | None = None,
    ) -> dict:
        pipeline_id = f"pipeline_{uuid4().hex[:12]}"
        work_item_id = str(work_item.get("id") or work_item.get("work_item_id") or uuid4().hex[:8])
        effective_context = build_effective_work_item_context(
            work_item,
            pipeline_state=None,
            ai_gen_comments=ai_gen_comments or [],
            approved_handoffs=[],
            team_comments=team_comments or [],
            epic_context=epic_context or {},
        )
        classification, template = route_work_item_to_template(
            work_item,
            refinement=refinement,
            effective_context=effective_context,
        )
        state = create_initial_pipeline_state(
            pipeline_id=pipeline_id,
            source=source,
            work_item_id=work_item_id,
            work_item=work_item,
            repo_context=repo_context,
            refinement=refinement,
            ai_gen_comments=ai_gen_comments or [],
            team_comments=team_comments or [],
            epic_context=epic_context or {},
            pipeline_context=self._pipeline_context_summary(effective_context, comment_count=len(ai_gen_comments or [])),
            workflow_template=template["name"],
            stage_order=list_stage_names(template),
            stage_metadata=stage_metadata_map(template),
            work_item_classification=classification,
        )
        state.activity.append({"type": "pipeline_created", "timestamp": utc_now(), "workflow_template": template["name"]})
        if ai_gen_comments:
            state.activity.append({"type": "comments_loaded", "timestamp": utc_now(), "count": len(ai_gen_comments)})
        if team_comments:
            state.activity.append({"type": "team_comments_loaded", "timestamp": utc_now(), "count": len(team_comments)})
        self.save_pipeline(state)
        _audit("pipeline_created", pipeline_id=state.pipeline_id,
               details={"workflow_template": template["name"], "work_item_id": work_item_id,
                        "work_item_type": str(state.work_item.get("type") or "")})
        return self._serialize_pipeline(state)

    def get_pipeline(self, pipeline_id: str) -> dict:
        state = self.load_pipeline(pipeline_id)
        return self._serialize_pipeline(state)

    def get_pipeline_for_work_item(self, work_item_id: str | int) -> dict | None:
        state = self.load_latest_pipeline_for_work_item(work_item_id)
        return self._serialize_pipeline(state) if state else None

    def run_stage(self, pipeline_id: str, stage: str, regenerate: bool = False, ai_gen_comments: list[dict] | None = None, team_comments: list[dict] | None = None) -> dict:
        state = self.load_pipeline(pipeline_id)
        self._log_stage_transition(state, stage, "run_requested", regenerate=regenerate)
        allowed, reason = can_run_stage(state, stage, regenerate=regenerate)
        if not allowed:
            self._log_stage_transition(state, stage, "run_blocked", regenerate=regenerate, reason=reason)
            raise ValueError(reason)
        if ai_gen_comments is not None:
            state.ai_gen_comments = ai_gen_comments
        if team_comments is not None:
            state.team_comments = team_comments
        stage_state = state.stages[stage]
        stage_state.version = stage_state.version + 1 if regenerate or stage_state.version else 1
        effective_context = self._rebuild_effective_context(state)
        has_effective_feedback = bool(effective_context.get("clarifications") or effective_context.get("pipeline_feedback"))
        if regenerate or (stage == "ba" and has_effective_feedback):
            state.refinement = self._refresh_refinement_from_effective_context(state, effective_context)
        state.pipeline_context = self._pipeline_context_summary(effective_context, comment_count=len(state.ai_gen_comments))
        review_context = self._build_review_context(stage_state) if regenerate else None
        output = self._run_stage_output(state, stage, effective_context=effective_context, review_context=review_context)
        critic = self._run_critic_for_stage(stage, output, state)
        unresolved, resolved = self._split_findings(stage_state, critic)
        stage_state.output = output
        stage_state.critic = critic
        stage_state.status = self._stage_status_after_run(state, stage, output, critic)
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
        self._sync_stage_drafts(state, stage, output)
        self._log_stage_transition(
            state,
            stage,
            "run_completed",
            regenerate=regenerate,
            status=stage_state.status,
            approved=stage_state.approved,
            draft_count=len(flatten_drafts(state.draft_work_items)),
        )
        state.activity.append(
            {
                "type": "stage_generated" if not regenerate else "stage_regenerated",
                "timestamp": utc_now(),
                "stage": stage,
                "version": stage_state.version,
            }
        )
        state.current_stage = stage
        self._touch_pipeline(state)
        self.save_pipeline(state)
        _audit("stage_generated", pipeline_id=pipeline_id, stage=stage,
               details={"regenerate": regenerate, "status": stage_state.status, "version": stage_state.version})
        return self._serialize_pipeline(state)

    def run_epic_plan(self, pipeline_id: str, ai_gen_comments: list[dict] | None = None, team_comments: list[dict] | None = None) -> dict:
        state = self.load_pipeline(pipeline_id)
        if state.workflow_template != "epic_planning":
            raise ValueError("run_epic_plan is only supported for epic_planning workflows.")
        self._log_stage_transition(state, "epic_plan", "workflow_requested", workflow_template=state.workflow_template)
        if ai_gen_comments is not None:
            state.ai_gen_comments = ai_gen_comments
        if team_comments is not None:
            state.team_comments = team_comments
        errors: list[str] = []
        for stage in ["epic_analysis", "feature_generation", "story_generation", "review"]:
            try:
                stage_state = state.stages.get(stage)
                if not stage_state:
                    continue
                self._log_stage_transition(
                    state,
                    stage,
                    "workflow_stage_start",
                    status=stage_state.status,
                    has_output=bool(stage_state.output),
                    approved=stage_state.approved,
                )
                if not stage_state.output:
                    output = self._run_stage_output(state, stage, effective_context=self._rebuild_effective_context(state))
                    critic = self._run_critic_for_stage(stage, output, state)
                    unresolved, resolved = self._split_findings(stage_state, critic)
                    stage_state.output = output
                    stage_state.critic = critic
                    stage_state.status = self._stage_status_after_run(state, stage, output, critic)
                    stage_state.version = stage_state.version + 1 if stage_state.version else 1
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
                    self._sync_stage_drafts(state, stage, output)
                    self._log_stage_transition(
                        state,
                        stage,
                        "workflow_stage_generated",
                        status=stage_state.status,
                        finding_count=len(unresolved),
                        draft_count=len(flatten_drafts(state.draft_work_items)),
                    )
                    state.activity.append({"type": "stage_generated", "timestamp": utc_now(), "stage": stage, "version": stage_state.version})
                if stage != "review":
                    stage_state = state.stages[stage]
                    stage_state.approved = True
                    stage_state.approved_at = utc_now()
                    stage_state.approved_by = "system_epic_orchestrator"
                    stage_state.status = "approved"
                    if stage_state.handoff_id:
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
                    state.activity.append({"type": "stage_approved", "timestamp": utc_now(), "stage": stage, "approved_by": "system_epic_orchestrator"})
                    self._unlock_after_epic_internal_stage(state, stage)
                    self._log_stage_transition(
                        state,
                        stage,
                        "workflow_stage_approved",
                        next_stage=self._active_stage_name(state),
                        draft_count=len(flatten_drafts(state.draft_work_items)),
                    )
            except Exception as error:
                errors.append(f"{stage}: {error}")
                self._log_stage_transition(state, stage, "workflow_stage_failed", error=type(error).__name__, message=str(error))
                break
        if errors:
            state.pipeline_context = {
                **state.pipeline_context,
                "warnings": list(dict.fromkeys([*list(state.pipeline_context.get("warnings", [])), *errors])),
            }
            state.activity.append({"type": "epic_plan_partial", "timestamp": utc_now(), "errors": errors})
            self._log_stage_transition(state, "epic_plan", "workflow_partial", errors=errors)
        state.current_stage = "review" if state.stages.get("review", StageState("review")).output else self._active_stage_name(state)
        self._log_stage_transition(
            state,
            "epic_plan",
            "workflow_completed",
            current_stage=state.current_stage,
            workflow_state=self._workflow_status(state)[0],
            draft_count=len(flatten_drafts(state.draft_work_items)),
        )
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
        state.activity.append({"type": "stage_approved", "timestamp": utc_now(), "stage": stage, "approved_by": approved_by})
        state.activity.append({"type": "handoff_created", "timestamp": utc_now(), "stage": stage, "handoff_id": handoff["handoff_id"]})
        self._log_stage_transition(state, stage, "approval_completed", approved_by=approved_by, next_stage=self._active_stage_name(state))
        state.pipeline_context = self._pipeline_context_summary(self._rebuild_effective_context(state), comment_count=len(state.ai_gen_comments))
        self._touch_pipeline(state)
        self.save_pipeline(state)
        _audit("stage_approved", pipeline_id=pipeline_id, stage=stage,
               actor=approved_by or "azure_devops",
               details={"version": stage_state.version, "handoff_id": handoff["handoff_id"]})
        return self._serialize_pipeline(state)

    def skip_stage(self, pipeline_id: str, stage: str, reason: str) -> dict:
        state = self.load_pipeline(pipeline_id)
        state = apply_skip(state, stage, reason=reason)
        state.pipeline_context = self._pipeline_context_summary(self._rebuild_effective_context(state), comment_count=len(state.ai_gen_comments))
        self._touch_pipeline(state)
        self.save_pipeline(state)
        _audit("stage_skipped", pipeline_id=pipeline_id, stage=stage,
               details={"reason": reason})
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
        state.activity.append({"type": "clarification_added", "timestamp": feedback.timestamp, "stage": stage, "author": feedback.author})
        state.pipeline_context = self._pipeline_context_summary(self._rebuild_effective_context(state), comment_count=len(state.ai_gen_comments))
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

    def get_draft_work_items(self, pipeline_id: str) -> dict:
        state = self.load_pipeline(pipeline_id)
        return {
            "pipeline_id": state.pipeline_id,
            "workflow_template": state.workflow_template,
            "draft_work_items": list(state.draft_work_items),
        }

    def approve_draft_work_items(self, pipeline_id: str, draft_ids: list[str]) -> dict:
        state = self.load_pipeline(pipeline_id)
        state.draft_work_items = approve_drafts(state.draft_work_items, draft_ids)
        self._touch_pipeline(state)
        self.save_pipeline(state)
        return self.get_draft_work_items(pipeline_id)

    def create_draft_work_items(self, pipeline_id: str, draft_ids: list[str], create_child_tasks: bool = True) -> dict:
        state = self.load_pipeline(pipeline_id)
        selected = self._select_drafts(state.draft_work_items, draft_ids, create_child_tasks=create_child_tasks)
        return {
            "pipeline_id": state.pipeline_id,
            "work_item_create_requests": build_create_requests(selected),
        }

    def mark_draft_work_items_created(self, pipeline_id: str, created_items: list[dict]) -> dict:
        state = self.load_pipeline(pipeline_id)
        state.draft_work_items = mark_drafts_created(state.draft_work_items, created_items)
        owner_stage = self._draft_owner_stage(state)
        if owner_stage:
            state.stages[owner_stage].output["created_work_items"] = created_items
            if state.stages[owner_stage].handoff_id:
                handoff = load_handoff(state.stages[owner_stage].handoff_id)
                if handoff:
                    handoff["content"]["created_work_items"] = created_items
                    handoff["next_actions"] = ["Review created Azure DevOps items.", "Retry failed draft items if needed."]
                    save_handoff(handoff)
        state.activity.append(
            {
                "type": "work_item_creation_result",
                "timestamp": utc_now(),
                "created_items": created_items,
            }
        )
        self._touch_pipeline(state)
        self.save_pipeline(state)
        return self.get_draft_work_items(pipeline_id)

    def _run_stage_output(
        self,
        state: PipelineState,
        stage: str,
        effective_context: dict | None = None,
        review_context: dict | None = None,
    ) -> dict:
        return run_stage_output(
            stage,
            state,
            approved_stage_context=lambda stage_name: self._approved_stage_context(state, stage_name),
            effective_context=effective_context or self._rebuild_effective_context(state),
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

    def _unlock_after_epic_internal_stage(self, state: PipelineState, stage: str) -> None:
        order = state.stage_order
        if stage not in order:
            return
        index = order.index(stage)
        if index + 1 >= len(order):
            return
        next_stage = state.stages.get(order[index + 1])
        if next_stage and next_stage.status == "locked":
            next_stage.status = "pending"
            self._log_stage_transition(state, stage, "next_stage_unlocked", next_stage=next_stage.stage, next_status=next_stage.status)

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
        workflow_state, workflow_summary = self._workflow_status(state)
        created_items = self._created_work_items(state)
        data["allowed_actions"] = self._allowed_actions(state)
        data["current_stage"] = self._active_stage_name(state)
        data["workflow_state"] = workflow_state
        data["workflow_summary"] = workflow_summary
        data["workflow_template"] = state.workflow_template
        data["stage_order"] = list(state.stage_order)
        data["stage_metadata"] = state.stage_metadata
        data["work_item_classification"] = state.work_item_classification
        data["pipeline_context"] = state.pipeline_context
        data["activity"] = list(state.activity)
        data["draft_work_items"] = list(state.draft_work_items)
        data["created_work_items"] = created_items
        data["current_stage_findings"] = self._current_stage_findings(state)
        data["current_stage_blocking_findings"] = self._current_stage_blocking_findings(state)
        data["all_findings"] = self._all_findings(state)
        data["resolved_findings"] = self._resolved_findings(state)
        data["context_warnings"] = list(state.pipeline_context.get("warnings", [])) if isinstance(state.pipeline_context, dict) else []
        print(
            "ai-gen pipeline"
            f" current_stage={data['current_stage']}"
            f" current_stage_findings={len(data['current_stage_findings'])}"
            f" current_stage_blocking_findings={len(data['current_stage_blocking_findings'])}"
            f" all_findings={len(data['all_findings'])}"
            f" resolved_findings={len(data['resolved_findings'])}"
            f" context_sources={len((data.get('pipeline_context') or {}).get('context_sources', []))}"
        )
        return data

    def _allowed_actions(self, state: PipelineState) -> dict[str, list[str]]:
        current_stage = self._active_stage_name(state)
        workflow_state, _ = self._workflow_status(state)
        current_handoff_status = self._current_handoff_status(state, current_stage)
        actions = {
            "generate_stages": [],
            "regenerate_stages": [],
            "approve_stages": [],
            "skip_stages": [],
            "view_handoff_stages": [],
            "feedback_stages": [],
            "current_stage_actions": [],
            "workflow_actions": get_allowed_actions(
                state.workflow_template,
                workflow_state,
                len(flatten_drafts(state.draft_work_items)),
                current_handoff_status,
            ),
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

    def _workflow_status(self, state: PipelineState) -> tuple[str, str]:
        snapshot = WorkflowSnapshot(
            workflow_template=state.workflow_template,
            stages={name: stage.to_dict() for name, stage in state.stages.items()},
            draft_work_items=list(state.draft_work_items),
        )
        machine = get_state_machine(state.workflow_template, snapshot)
        workflow_state = machine.derive_state()
        return workflow_state, machine.summary_for(workflow_state)

    def _current_handoff_status(self, state: PipelineState, stage_name: str) -> str | None:
        preferred = [stage_name]
        if state.workflow_template == "task_execution":
            preferred = ["dev_packet", "test_checklist", stage_name]
        elif state.workflow_template == "bug_fix":
            preferred = ["fix_packet", "regression_tests", stage_name]
        elif state.workflow_template == "story_delivery":
            preferred = ["task_planning", "test_planning", stage_name]
        for candidate in preferred:
            stage_state = state.stages.get(candidate)
            if stage_state and stage_state.handoff_id:
                handoff = load_handoff(stage_state.handoff_id)
                if handoff:
                    return str(handoff.get("status", "")).strip() or None
        return None

    def _created_work_items(self, state: PipelineState) -> list[dict]:
        created: list[dict] = []
        for draft in flatten_drafts(state.draft_work_items):
            if draft.get("status") != "created" or not draft.get("azure_work_item_id"):
                continue
            created.append(
                {
                    "draft_id": draft.get("draft_id"),
                    "type": draft.get("draft_type"),
                    "title": draft.get("title"),
                    "azure_work_item_id": draft.get("azure_work_item_id"),
                    "parent_azure_work_item_id": draft.get("parent_azure_work_item_id"),
                    "parent_draft_id": draft.get("parent_draft_id"),
                }
            )
        return created

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

    def _stage_status_after_run(self, state: PipelineState, stage: str, output: dict, critic: dict | None) -> str:
        if (critic or {}).get("decision") == "needs_revision":
            return "needs_revision"
        if state.workflow_template == "story_delivery" and stage in {"ba", "ui_optional"}:
            if list(output.get("unknowns") or []):
                return "needs_revision"
        return "generated"

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

    def _log_stage_transition(self, state: PipelineState, stage: str, event: str, **details: object) -> None:
        serialized = " ".join(
            f"{key}={details[key]!r}" for key in sorted(details) if details[key] is not None
        )
        message = (
            f"ai-gen stage-transition pipeline_id={state.pipeline_id} workflow_template={state.workflow_template} "
            f"stage={stage} event={event}"
        )
        if serialized:
            message = f"{message} {serialized}"
        print(message)

    def _is_optional_stage(self, state: PipelineState, stage_name: str) -> bool:
        return bool(state.stage_metadata.get(stage_name, {}).get("optional"))

    def _is_optional_stage_name(self, stage_name: str) -> bool:
        return stage_name.endswith("_optional")

    def _sync_stage_drafts(self, state: PipelineState, stage: str, output: dict) -> None:
        proposed = output.get("generated_work_items") or output.get("proposed_work_items")
        if not isinstance(proposed, list):
            return
        stage_drafts = []
        for item in proposed:
            if isinstance(item, dict):
                copy = dict(item)
                copy.setdefault("source_stage", stage)
                stage_drafts.append(copy)
        preserved = [draft for draft in state.draft_work_items if draft.get("source_stage") != stage]
        state.draft_work_items = preserved + normalize_drafts(stage_drafts)

    def _select_drafts(self, drafts: list[dict], draft_ids: list[str], create_child_tasks: bool = True) -> list[dict]:
        selected_ids = {str(item).strip() for item in draft_ids if str(item).strip()}
        selected: list[dict] = []
        for draft in normalize_drafts(drafts):
            selected.extend(self._select_drafts_recursive(draft, selected_ids, create_child_tasks))
        return normalize_drafts(selected)

    def _flatten_nested_drafts(self, draft: dict) -> list[dict]:
        item = dict(draft)
        children = item.get("children") or item.get("child_drafts") or []
        flattened = [item]
        for child in children:
            if isinstance(child, dict):
                flattened.extend(self._flatten_nested_drafts(child))
        return flattened

    def _select_drafts_recursive(self, draft: dict, selected_ids: set[str], create_child_tasks: bool) -> list[dict]:
        item = dict(draft)
        draft_id = str(item.get("draft_id", "")).strip()
        children = [dict(child) for child in item.get("children") or item.get("child_drafts") or [] if isinstance(child, dict)]
        if draft_id in selected_ids:
            if create_child_tasks:
                return [item]
            item["children"] = []
            item["child_drafts"] = []
            return [item]
        selected_children: list[dict] = []
        for child in children:
            selected_children.extend(self._select_drafts_recursive(child, selected_ids, create_child_tasks))
        return selected_children

    def _rebuild_effective_context(self, state: PipelineState) -> dict:
        return build_effective_work_item_context(
            state.work_item,
            pipeline_state=state.to_dict(),
            ai_gen_comments=state.ai_gen_comments,
            approved_handoffs=self._approved_handoffs(state),
            team_comments=state.team_comments or [],
            epic_context=state.epic_context or {},
            question_answers=self._question_answers_from_state(state),
        )

    def _question_answers_from_state(self, state: PipelineState) -> list[dict]:
        """Extract Q&A pairs from stage review_feedback (stored by answer-questions endpoint)."""
        qa: list[dict] = []
        for stage_state in state.stages.values():
            for feedback in stage_state.review_feedback:
                body = str(feedback.comment or "").strip()
                if body.startswith("Q:") and "\nA:" in body:
                    lines = body.split("\nA:", 1)
                    q = lines[0].replace("Q:", "", 1).strip()
                    a = lines[1].strip() if len(lines) > 1 else ""
                    if q and a:
                        qa.append({"question": q, "answer": a})
        return qa

    def _refresh_refinement_from_effective_context(self, state: PipelineState, effective_context: dict) -> dict:
        query = str(effective_context.get("effective_text") or state.work_item.get("title") or "").strip()
        if not query:
            return state.refinement
        context = {
            "source": state.source,
            "work_item": state.work_item,
            "constraints": list((state.refinement or {}).get("validations", [])),
            "repo_hints": state.repo_context.get("session_bias_summary") or {},
        }
        refreshed = refine_task(query, context)
        candidate = dict(refreshed.get("refinement") or {})
        if not candidate:
            return state.refinement
        return _merge_refinement(state.refinement, candidate)

    def _approved_handoffs(self, state: PipelineState) -> list[dict]:
        output: list[dict] = []
        for stage_name in state.stage_order:
            stage_state = state.stages.get(stage_name)
            if not stage_state or not stage_state.approved or not stage_state.handoff_id:
                continue
            handoff = load_handoff(stage_state.handoff_id)
            if handoff:
                output.append(handoff)
        return output

    def _pipeline_context_summary(self, effective_context: dict, comment_count: int) -> dict:
        return {
            "effective_context_summary": {
                "clarification_count": len(effective_context.get("clarifications", [])),
                "approval_count": len(effective_context.get("approvals", [])),
                "handoff_summary_count": len(effective_context.get("handoff_summaries", [])),
                "revision_note_count": len(effective_context.get("revision_notes", [])),
                "pipeline_feedback_count": len(effective_context.get("pipeline_feedback", [])),
                "effective_text_preview": str(effective_context.get("effective_text", ""))[:1200],
            },
            "context_sources": list(effective_context.get("context_sources", [])),
            "last_comment_sync_at": utc_now() if comment_count else None,
            "comment_count": comment_count,
            "warnings": list(effective_context.get("warnings", [])),
        }

    def _draft_owner_stage(self, state: PipelineState) -> str | None:
        for stage_name in reversed(state.stage_order):
            stage_state = state.stages.get(stage_name)
            if stage_state and stage_state.output and (
                stage_state.output.get("generated_work_items") or stage_state.output.get("proposed_work_items")
            ):
                return stage_name
        return None


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for finding in findings:
        finding_id = str(finding.get("id", "")).strip()
        if finding_id and finding_id not in seen:
            seen.add(finding_id)
            output.append(finding)
    return output


def _merge_refinement(existing: dict | None, candidate: dict) -> dict:
    merged = dict(existing or {})
    candidate = _normalize_refinement_candidate(candidate)
    override_keys = {"base_flows"}
    stable_keys = {"variants", "surfaces"}
    enrich_keys = {
        "fields",
        "validations",
        "scope_hints",
        "first_pass_scope",
        "actors",
        "states",
        "unknowns",
        "focus_rules",
    }
    for key in override_keys | stable_keys | enrich_keys:
        if key not in candidate and key not in merged:
            continue
        existing_values = list(merged.get(key, []))
        candidate_values = list(candidate.get(key, []))
        if key in override_keys and candidate_values:
            merged[key] = _dedupe_text(candidate_values)
        elif key in stable_keys and existing_values:
            merged[key] = _dedupe_text(existing_values)
        else:
            merged[key] = _dedupe_text(existing_values + candidate_values)
    scalar_keys = ["base_flow", "variant", "surface", "flow_suggestion", "confidence"]
    for key in scalar_keys:
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def _normalize_refinement_candidate(candidate: dict) -> dict:
    normalized = dict(candidate or {})
    list_normalizers = {
        "base_flows": normalize_flow,
        "variants": normalize_variant,
        "surfaces": normalize_surface,
        "fields": normalize_field,
        "validations": normalize_validation,
    }
    for key, normalizer in list_normalizers.items():
        values = normalized.get(key)
        if not isinstance(values, list):
            continue
        normalized[key] = [item for item in (normalizer(str(value)) for value in values) if item]
    scalar_normalizers = {
        "base_flow": normalize_flow,
        "variant": normalize_variant,
        "surface": normalize_surface,
    }
    for key, normalizer in scalar_normalizers.items():
        value = normalized.get(key)
        if value is None:
            continue
        normalized_value = normalizer(str(value))
        if normalized_value:
            normalized[key] = normalized_value
        else:
            normalized.pop(key, None)
    return normalized


def _dedupe_text(values: list) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output
