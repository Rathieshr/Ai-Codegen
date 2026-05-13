"""Build handoff artifacts from pipeline stage outputs."""

from __future__ import annotations

from backend.handoff.schemas import default_handoff, make_handoff_id


def build_handoff(
    pipeline_state,
    stage: str,
    stage_output: dict,
    refinement: dict | None = None,
    repo_context: dict | None = None,
    status: str = "draft",
) -> dict:
    """Create a structured handoff artifact for a pipeline stage."""

    stage_state = pipeline_state.stages[stage]
    version = max(stage_state.version, 1)
    handoff_id = make_handoff_id(pipeline_state.work_item_id, stage, version)
    handoff = default_handoff(
        handoff_id=handoff_id,
        pipeline_id=pipeline_state.pipeline_id,
        work_item_id=pipeline_state.work_item_id,
        stage=stage,
        version=version,
        source_stage=stage,
        target_stages=_target_stages(stage),
    )
    handoff["status"] = status
    handoff["approved_at"] = stage_state.approved_at if status == "approved" else None
    handoff["summary"] = _summary(stage, stage_output)
    handoff["content"] = stage_output
    handoff["refinement"] = refinement or {}
    handoff["repo_context"] = _trim_repo_context(repo_context or {})
    handoff["constraints"] = _constraints(stage_output)
    handoff["open_questions"] = _open_questions(stage_output)
    handoff["next_actions"] = _next_actions(stage, stage_output)
    return handoff


def _target_stages(stage: str) -> list[str]:
    mapping = {
        "ba": ["ui", "dev", "test"],
        "ui": ["dev", "test"],
        "dev": ["test", "validation", "developer"],
        "test": ["qa", "validation"],
        "critic": ["owner", "approver"],
    }
    return mapping.get(stage, [])


def _summary(stage: str, stage_output: dict) -> str:
    if stage == "ba":
        return stage_output.get("refined_requirement", "Business requirement handoff")
    if stage == "ui":
        return stage_output.get("screen_name", "UI handoff")
    if stage == "dev":
        return stage_output.get("task_summary", "Development handoff")
    if stage == "test":
        return f"{len(stage_output.get('test_cases', []))} test cases prepared for review."
    if stage == "critic":
        return stage_output.get("decision", "Critic review")
    return f"{stage.title()} handoff"


def _constraints(stage_output: dict) -> list[str]:
    if "constraints" in stage_output:
        return list(stage_output.get("constraints", []))[:8]
    if "business_rules" in stage_output:
        return list(stage_output.get("business_rules", []))[:8]
    return []


def _open_questions(stage_output: dict) -> list[str]:
    return list(stage_output.get("unknowns", []))[:8]


def _next_actions(stage: str, stage_output: dict) -> list[str]:
    if stage == "ba":
        return ["Review the clarified requirement.", "Approve BA output before UI or dev work."]
    if stage == "ui":
        return ["Confirm the UI structure and field behavior.", "Approve UI output or skip with reason."]
    if stage == "dev":
        return ["Review the execution packet and selected scope.", "Approve before test planning."]
    if stage == "test":
        return ["Review positive, negative, edge, and acceptance cases.", "Approve before validation or QA handoff."]
    if stage == "critic":
        return list(stage_output.get("recommended_changes", []))[:4] or ["Resolve critic findings before continuing."]
    return []


def _trim_repo_context(repo_context: dict) -> dict:
    keys = ["resolved_repo_id", "resolved_branch_name", "selected_execution_files", "related_flows", "detected_flow"]
    output = {}
    for key in keys:
        if key in repo_context and repo_context[key]:
            output[key] = repo_context[key]
    return output
