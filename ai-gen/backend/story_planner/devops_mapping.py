from __future__ import annotations

from typing import Any

from .models import PlannerSession, TaskDraft


def build_creation_preview(session: PlannerSession) -> dict[str, Any]:
    return {
        "story": {
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
        },
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
            "Microsoft.VSTS.Scheduling.StoryPoints": task.estimated_effort or None,
        },
    }


def _escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
