from __future__ import annotations

from typing import Any

from .models import PlannerSession, TaskDraft


def build_creation_preview(session: PlannerSession) -> dict[str, Any]:
    story_preview = None if session.planner_kind == "user_story" else {
        "type": "User Story",
        "title": session.title,
        "description": session.description,
        "business_value": session.business_value,
        "acceptance_criteria": list(session.acceptance_criteria),
        "fields": {
            "System.Title": session.title,
            "System.Description": build_story_description(session),
            "Microsoft.VSTS.Common.AcceptanceCriteria": build_acceptance_html(session.acceptance_criteria),
        },
    }
    return {
        "mode": session.planner_kind,
        "parent_work_item_id": session.source_work_item_id,
        "parent_work_item_type": session.source_work_item_type,
        "story": story_preview,
        "tasks": [build_task_preview(task) for task in session.tasks],
    }


def build_story_description(session: PlannerSession) -> str:
    return f"<p>{_escape_html(session.description)}</p><p><strong>Business Value:</strong> {_escape_html(session.business_value)}</p>"


def build_acceptance_html(items: list[str]) -> str:
    body = "".join(f"<li>{_escape_html(item)}</li>" for item in items)
    return f"<ul>{body}</ul>"


def build_task_preview(task: TaskDraft) -> dict[str, Any]:
    return {
        "id": task.id,
        "type": "Task",
        "title": task.title,
        "description": task.description,
        "estimated_effort": task.estimated_effort,
        "fields": {
            "System.Title": task.title,
            "System.Description": f"<p>{_escape_html(task.description)}</p>",
        },
    }


def _escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
