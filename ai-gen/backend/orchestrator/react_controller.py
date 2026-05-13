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
from backend.orchestrator.pipeline_state import PipelineState, StageState, create_initial_pipeline_state, utc_now
from backend.repo_context.storage import read_json, write_json


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
        state = create_initial_pipeline_state(
            pipeline_id=pipeline_id,
            source=source,
            work_item_id=work_item_id,
            work_item=work_item,
            repo_context=repo_context,
            refinement=refinement,
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
        output = self._run_stage_output(state, stage)
        critic = self._run_critic_for_stage(stage, output, state)
        stage_state.output = output
        stage_state.critic = critic
        stage_state.status = "needs_revision" if critic.get("decision") == "needs_revision" else "generated"
        stage_state.approved = False
        stage_state.approved_at = None
        stage_state.approved_by = None
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

    def _run_stage_output(self, state: PipelineState, stage: str) -> dict:
        if stage == "ba":
            return run_ba_assistant(state.work_item, state.refinement)
        if stage == "ui":
            ba_output = state.stages["ba"].output
            return run_app_ui_assistant(ba_output, state.refinement)
        if stage == "dev":
            return run_dev_assistant(
                ba_output=state.stages["ba"].output,
                ui_output=state.stages["ui"].output if state.stages["ui"].output else None,
                repo_context=state.repo_context,
                refinement=state.refinement,
            )
        if stage == "test":
            return run_test_assistant(
                ba_output=state.stages["ba"].output,
                dev_output=state.stages["dev"].output,
                ui_output=state.stages["ui"].output if state.stages["ui"].output else None,
            )
        if stage == "critic":
            return run_critic_assistant(
                ba_output=state.stages["ba"].output if state.stages["ba"].output else None,
                ui_output=state.stages["ui"].output if state.stages["ui"].output else None,
                dev_output=state.stages["dev"].output if state.stages["dev"].output else None,
                test_output=state.stages["test"].output if state.stages["test"].output else None,
            )
        raise ValueError(f"Unknown stage: {stage}")

    def _run_critic_for_stage(self, stage: str, output: dict, state: PipelineState) -> dict:
        if stage == "ba":
            return run_critic_assistant(ba_output=output)
        if stage == "ui":
            return run_critic_assistant(ba_output=state.stages["ba"].output, ui_output=output)
        if stage == "dev":
            return run_critic_assistant(
                ba_output=state.stages["ba"].output,
                ui_output=state.stages["ui"].output if state.stages["ui"].output else None,
                dev_output=output,
            )
        if stage == "test":
            return run_critic_assistant(
                ba_output=state.stages["ba"].output,
                ui_output=state.stages["ui"].output if state.stages["ui"].output else None,
                dev_output=state.stages["dev"].output,
                test_output=output,
            )
        return run_critic_assistant(
            ba_output=state.stages["ba"].output if state.stages["ba"].output else None,
            ui_output=state.stages["ui"].output if state.stages["ui"].output else None,
            dev_output=state.stages["dev"].output if state.stages["dev"].output else None,
            test_output=state.stages["test"].output if state.stages["test"].output else None,
        )

    def _touch_pipeline(self, state: PipelineState) -> None:
        state.version += 1
        state.updated_at = utc_now()

    def _serialize_pipeline(self, state: PipelineState) -> dict:
        data = state.to_dict()
        data["allowed_actions"] = self._allowed_actions(state)
        return data

    def _allowed_actions(self, state: PipelineState) -> dict[str, list[str]]:
        actions = {
            "generate_stages": [],
            "regenerate_stages": [],
            "approve_stages": [],
            "skip_stages": [],
            "view_handoff_stages": [],
        }
        for stage_name, stage_state in state.stages.items():
            if stage_state.status != "locked" and not stage_state.approved:
                actions["generate_stages"].append(stage_name)
            if stage_state.status in {"generated", "needs_revision", "approved"}:
                actions["regenerate_stages"].append(stage_name)
            if bool(stage_state.output) and stage_state.status != "locked" and not stage_state.approved:
                actions["approve_stages"].append(stage_name)
            if stage_name == "ui" and stage_state.status != "locked" and not stage_state.approved:
                actions["skip_stages"].append(stage_name)
            if stage_state.handoff_id:
                actions["view_handoff_stages"].append(stage_name)
        return actions
