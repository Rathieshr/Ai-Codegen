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
        target_stages=_target_stages(pipeline_state, stage),
    )
    handoff["status"] = status
    handoff["approved_at"] = stage_state.approved_at if status == "approved" else None
    handoff["handoff_type"] = _handoff_type(stage)
    handoff["summary"] = _summary(stage, stage_output)
    handoff["content"] = stage_output
    handoff["refinement"] = refinement or {}
    handoff["repo_context"] = _trim_repo_context(repo_context or {})
    handoff["constraints"] = _constraints(stage_output)
    handoff["open_questions"] = _open_questions(stage_output)
    handoff["next_actions"] = _next_actions(stage, stage_output)
    return handoff


def _target_stages(pipeline_state, stage: str) -> list[str]:
    order = list(getattr(pipeline_state, "stage_order", []) or [])
    if stage in order:
        index = order.index(stage)
        return order[index + 1:index + 3]
    mapping = {
        "ba": ["ui", "dev", "test"],
        "ui": ["dev", "test"],
        "ui_optional": ["task_planning", "test_planning"],
        "task_planning": ["test_planning", "developer", "qa"],
        "test_planning": ["critic", "qa"],
        "dev": ["test", "validation", "developer"],
        "dev_packet": ["test_checklist", "developer"],
        "fix_packet": ["regression_tests", "developer"],
        "test": ["qa", "validation"],
        "critic": ["owner", "approver"],
        "story_generation": ["review"],
        "feature_analysis": ["story_generation"],
        "epic_analysis": ["story_generation"],
        "review": ["owner", "approver"],
        "ui_handoff": ["developer", "qa"],
    }
    return mapping.get(stage, [])


def _summary(stage: str, stage_output: dict) -> str:
    if stage == "ba":
        return stage_output.get("refined_requirement", "Business requirement handoff")
    if stage == "ui":
        return stage_output.get("screen_name", "UI handoff")
    if stage in {"ui_optional", "ui_plan", "ui_handoff"}:
        return stage_output.get("summary") or stage_output.get("screen_name", "UI handoff")
    if stage == "dev":
        return stage_output.get("task_summary", "Development handoff")
    if stage in {"dev_packet", "fix_packet"}:
        return stage_output.get("task_summary", "Execution packet handoff")
    if stage == "test":
        return f"{len(stage_output.get('test_cases', []))} test cases prepared for review."
    if stage in {"test_planning", "test_design", "regression_tests", "test_checklist"}:
        return stage_output.get("summary") or f"{len(stage_output.get('test_cases', []))} test items prepared."
    if stage in {"epic_analysis", "feature_analysis", "story_generation", "review", "task_planning", "task_analysis", "bug_analysis", "impact_analysis", "research_plan", "findings", "recommendation"}:
        return stage_output.get("summary", f"{stage.title()} handoff")
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
    if stage == "ui_optional":
        return ["Review the optional UI planning output.", "Approve or skip the UI stage before task planning."]
    if stage == "dev":
        return ["Review the execution packet and selected scope.", "Approve before test planning."]
    if stage in {"dev_packet", "fix_packet"}:
        return ["Review the execution packet.", "Approve before handing work to implementation."]
    if stage == "test":
        return ["Review positive, negative, edge, and acceptance cases.", "Approve before validation or QA handoff."]
    if stage in {"test_planning", "test_design", "regression_tests", "test_checklist"}:
        return ["Review the planned validation coverage.", "Approve before downstream QA or validation work."]
    if stage == "task_planning":
        return ["Review the proposed child tasks.", "Approve before copying tasks into downstream systems."]
    if stage == "story_generation":
        return ["Review the proposed stories.", "Approve before feature or epic review sign-off."]
    if stage in {"epic_analysis", "feature_analysis", "review", "task_analysis", "bug_analysis", "impact_analysis", "research_plan", "findings", "recommendation"}:
        return ["Review the planning artifact.", "Approve before moving to the next workflow stage."]
    if stage == "critic":
        return list(stage_output.get("recommended_changes", []))[:4] or ["Resolve critic findings before continuing."]
    return []


def _handoff_type(stage: str) -> str:
    mapping = {
        "ba": "requirement_handoff",
        "ui": "ui_handoff",
        "ui_optional": "ui_handoff",
        "ui_plan": "ui_handoff",
        "ui_handoff": "ui_handoff",
        "dev": "dev_handoff",
        "dev_packet": "dev_handoff",
        "fix_packet": "bug_fix_handoff",
        "test": "test_handoff",
        "test_planning": "test_handoff",
        "test_design": "test_handoff",
        "regression_tests": "test_handoff",
        "test_checklist": "test_handoff",
        "task_planning": "story_generation_handoff",
        "task_analysis": "dev_handoff",
        "bug_analysis": "bug_fix_handoff",
        "impact_analysis": "bug_fix_handoff",
        "story_generation": "story_generation_handoff",
        "epic_analysis": "requirement_handoff",
        "feature_analysis": "requirement_handoff",
        "review": "requirement_handoff",
        "research_plan": "requirement_handoff",
        "findings": "requirement_handoff",
        "recommendation": "requirement_handoff",
    }
    return mapping.get(stage, "generic_handoff")


def _trim_repo_context(repo_context: dict) -> dict:
    keys = ["resolved_repo_id", "resolved_branch_name", "selected_execution_files", "related_flows", "detected_flow"]
    output = {}
    for key in keys:
        if key in repo_context and repo_context[key]:
            output[key] = repo_context[key]
    return output
