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
    blocking_findings = [
        finding
        for finding in stage_state.unresolved_findings
        if finding.get("severity") == "blocking"
        and finding.get("status", "open") == "open"
        and finding.get("target_stage", stage) == stage
    ]
    if blocking_findings:
        raise ValueError(f"Stage {stage} still has blocking critic findings.")

    stage_state.status = "approved"
    stage_state.approved = True
    stage_state.approved_at = utc_now()
    stage_state.approved_by = approved_by
    stage_state.version = stage_state.version + 1 if stage_state.version else 1
    resolved = [dict(finding) for finding in stage_state.resolved_findings]
    for finding in stage_state.unresolved_findings:
        if finding.get("target_stage", stage) != stage:
            continue
        item = dict(finding)
        item["status"] = "resolved"
        resolved.append(item)
    stage_state.resolved_findings = _dedupe_findings(resolved)
    stage_state.unresolved_findings = [
        finding for finding in stage_state.unresolved_findings
        if finding.get("target_stage", stage) != stage
    ]
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
    """Unlock the next stage in the configured pipeline order when rules allow it."""

    order = list(getattr(pipeline_state, "stage_order", []) or [])
    if stage in order:
        index = order.index(stage)
        if index + 1 < len(order):
            _unlock_if_locked(pipeline_state, order[index + 1])
    pipeline_state.updated_at = utc_now()
    return pipeline_state


def _unlock_if_locked(pipeline_state: PipelineState, stage: str) -> None:
    stage_state = pipeline_state.stages.get(stage)
    if stage_state and stage_state.status == "locked":
        stage_state.status = "pending"


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for finding in findings:
        finding_id = str(finding.get("id", "")).strip()
        if finding_id and finding_id not in seen:
            seen.add(finding_id)
            output.append(finding)
    return output
