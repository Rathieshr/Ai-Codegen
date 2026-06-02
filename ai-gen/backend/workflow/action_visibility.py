"""Workflow-aware action visibility rules for Azure DevOps workspaces."""

from __future__ import annotations


def get_allowed_actions(
    workflow_template: str,
    workflow_state: str,
    draft_count: int,
    handoff_status: str | None,
) -> list[str]:
    if workflow_template == "epic_planning":
        if workflow_state == "not_generated":
            return ["generate_epic_plan"]
        if workflow_state == "generated":
            if draft_count == 0:
                return ["resume_epic_plan"]
            actions: list[str] = ["approve_plan"]
            actions.extend(["select_all", "deselect_all"])
            return actions
        if workflow_state == "review_ready":
            actions: list[str] = []
            if draft_count > 0:
                actions.append("approve_plan")
                actions.extend(["select_all", "deselect_all"])
            else:
                actions.append("resume_epic_plan")
            return actions
        if workflow_state == "approved":
            return ["create_selected_work_items"] if draft_count > 0 else []
        if workflow_state == "work_items_created":
            return ["view_created_work_items"]
        return []

    if workflow_template == "feature_planning":
        if workflow_state == "not_generated":
            return ["generate_feature_breakdown"]
        if workflow_state in {"stories_generated", "review"}:
            actions = ["approve_plan"]
            if draft_count > 0:
                actions.extend(["select_all", "deselect_all"])
            return actions
        if workflow_state == "approved":
            return ["create_selected_work_items"] if draft_count > 0 else []
        if workflow_state == "work_items_created":
            return ["view_created_work_items"]
        return []

    if workflow_template == "story_delivery":
        if workflow_state == "not_generated":
            return ["generate_story_plan"]
        if workflow_state == "needs_clarification":
            return ["add_clarification", "regenerate_with_clarifications"]
        if workflow_state == "planned":
            return ["approve_story", "regenerate_story"]
        if workflow_state == "approved":
            return ["generate_tasks"]
        if workflow_state == "tasks_generated":
            return ["view_handoff"] if handoff_status else []
        return []

    if workflow_template == "task_execution":
        if workflow_state == "not_generated":
            return ["generate_execution_packet"]
        if workflow_state == "packet_ready":
            actions = ["copy_execution_packet", "copy_json", "download"]
            if handoff_status == "approved":
                actions.append("open_in_vscode")
            return actions
        if workflow_state == "validated":
            actions = ["copy_execution_packet", "copy_json", "download"]
            if handoff_status == "approved":
                actions.append("open_in_vscode")
            return actions
        return []

    if workflow_template == "bug_fix":
        if workflow_state == "not_generated":
            return ["analyze_bug"]
        if workflow_state == "impact_analyzed":
            return ["generate_fix_packet"]
        if workflow_state == "fix_ready":
            return ["generate_regression_checklist"]
        if workflow_state == "validated":
            return ["view_handoff"] if handoff_status else []
        return []

    if workflow_template == "qa_task":
        if workflow_state == "not_generated":
            return ["design_tests"]
        if workflow_state == "test_plan_ready":
            return ["approve_plan"]
        return []

    if workflow_template == "ui_task":
        if workflow_state == "not_generated":
            return ["generate_ui_plan"]
        if workflow_state == "ui_plan_ready":
            return ["approve_plan"]
        if workflow_state == "handoff_pending":
            return ["generate_ui_handoff"]
        if workflow_state == "handoff_ready":
            actions = ["approve_plan"]
            if handoff_status:
                actions.append("view_handoff")
            return actions
        return ["view_handoff"] if handoff_status else []

    if workflow_template == "spike":
        if workflow_state == "not_generated":
            return ["start_research_plan"]
        if workflow_state == "research_ready":
            return ["complete_recommendation"]
        return []

    return []
