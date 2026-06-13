from __future__ import annotations

from typing import Any

from .models import PlannerSession, TaskDraft


def build_creation_preview(session: PlannerSession) -> dict[str, Any]:
    if session.planner_kind == "epic":
        return {
            "mode": session.planner_kind,
            "parent_work_item_id": session.source_work_item_id,
            "parent_work_item_type": session.source_work_item_type,
            "story": None,
            "features": [build_feature_preview(title, index) for index, title in enumerate(session.acceptance_criteria)],
            "tasks": [build_epic_story_preview(task, session.acceptance_criteria) for task in session.tasks],
        }

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
        "features": [],
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


def build_feature_preview(title: str, index: int) -> dict[str, Any]:
    feature_id = f"feature_{index}"
    return {
        "id": feature_id,
        "type": "Feature",
        "title": title,
        "description": f"Deliver the {title} capability as part of the approved Epic scope.",
        "fields": {
            "System.Title": title,
            "System.Description": f"<p>Deliver the {_escape_html(title)} capability as part of the approved Epic scope.</p>",
        },
    }


def build_epic_story_preview(task: TaskDraft, features: list[str]) -> dict[str, Any]:
    parent_feature = _match_feature(task.title, features)
    parent_index = features.index(parent_feature) if parent_feature in features else 0
    return {
        "id": task.id,
        "type": "User Story",
        "title": task.title,
        "description": task.description,
        "estimated_effort": task.estimated_effort,
        "parent_feature_id": f"feature_{parent_index}",
        "fields": {
            "System.Title": task.title,
            "System.Description": f"<p>{_escape_html(task.description)}</p>",
        },
    }


def _match_feature(story_title: str, features: list[str]) -> str:
    normalized_title = str(story_title or "").lower()
    for feature in features:
        if str(feature).lower() in normalized_title:
            return feature
    prefix = str(story_title or "").split(":", 1)[0].strip().lower()
    for feature in features:
        if prefix and prefix == str(feature).strip().lower():
            return feature
    return features[0] if features else ""


def _escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
