"""Approval and stage-unlocking rules for the structured pipeline."""

from __future__ import annotations

from backend.orchestrator.pipeline_state import PipelineState, utc_now


def can_run_stage(pipeline_state: PipelineState, stage: str, regenerate: bool = False) -> tuple[bool, str]:
    """Return whether a stage may run, plus a short explanation."""

    stage_state = pipeline_state.stages.get(stage)
    if stage_state is None:
        return False, f"Unknown stage: {stage}"
    if stage_state.status == "locked":
        return False, f"Stage {stage} is locked until its prerequisite stage is approved or skipped."
    if stage_state.approved and not regenerate:
        return False, f"Stage {stage} is already approved. Use regenerate=true to run it again."
    return True, "ok"


def approve_stage(pipeline_state: PipelineState, stage: str, approved_by: str | None = None) -> PipelineState:
    """Approve a generated stage and unlock its successor when allowed."""

    stage_state = pipeline_state.stages.get(stage)
    if stage_state is None:
        raise ValueError(f"Unknown stage: {stage}")
    if stage_state.status == "locked":
        raise ValueError(f"Stage {stage} is locked.")
    if not stage_state.output:
        raise ValueError(f"Stage {stage} has no output to approve.")

    stage_state.status = "approved"
    stage_state.approved = True
    stage_state.approved_at = utc_now()
    stage_state.approved_by = approved_by
    stage_state.version = stage_state.version + 1 if stage_state.version else 1
    pipeline_state.current_stage = stage
    pipeline_state.updated_at = utc_now()
    return unlock_next_stage(pipeline_state, stage)


def skip_stage(pipeline_state: PipelineState, stage: str, reason: str) -> PipelineState:
    """Skip a stage that is intentionally not needed."""

    stage_state = pipeline_state.stages.get(stage)
    if stage_state is None:
        raise ValueError(f"Unknown stage: {stage}")
    if stage_state.status == "locked":
        raise ValueError(f"Stage {stage} is locked.")
    stage_state.status = "skipped"
    stage_state.approved = True
    stage_state.skip_reason = reason
    stage_state.approved_at = utc_now()
    stage_state.version = stage_state.version + 1 if stage_state.version else 1
    pipeline_state.updated_at = utc_now()
    return unlock_next_stage(pipeline_state, stage)


def unlock_next_stage(pipeline_state: PipelineState, stage: str) -> PipelineState:
    """Unlock the next stage in the fixed pipeline order when rules allow it."""

    if stage == "ba":
        _unlock_if_locked(pipeline_state, "ui")
    elif stage == "ui":
        _unlock_if_locked(pipeline_state, "dev")
    elif stage == "dev":
        _unlock_if_locked(pipeline_state, "test")
    elif stage == "test":
        _unlock_if_locked(pipeline_state, "critic")
    pipeline_state.updated_at = utc_now()
    return pipeline_state


def _unlock_if_locked(pipeline_state: PipelineState, stage: str) -> None:
    stage_state = pipeline_state.stages.get(stage)
    if stage_state and stage_state.status == "locked":
        stage_state.status = "pending"
