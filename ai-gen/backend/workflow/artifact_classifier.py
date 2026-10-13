"""Classify work items into workflow-aware artifact types."""

from __future__ import annotations

from typing import Any


def classify_work_item(
    work_item: dict[str, Any],
    refinement: dict[str, Any] | None = None,
    effective_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Classify a work item into a workflow template and basic intent metadata."""

    refinement = refinement or {}
    effective_context = effective_context or {}
    work_item_type = _normalize_type(
        work_item.get("type")
        or work_item.get("work_item_type")
        or work_item.get("System.WorkItemType")
        or ""
    )
    title = str(work_item.get("title", "")).strip()
    description = str(work_item.get("description", "")).strip()
    area_path = str(work_item.get("areaPath") or work_item.get("area_path") or "").strip()
    tags = [str(tag).strip().lower() for tag in work_item.get("tags", []) if str(tag).strip()]
    effective_text = str(effective_context.get("effective_text", "")).strip()
    lowered = " ".join(part for part in [title, description, area_path, " ".join(tags), effective_text] if part).lower()
    surfaces = set(_normalized_list(refinement.get("refined_surfaces") or refinement.get("surfaces")))

    if work_item_type == "epic":
        return _classification("epic", "high", "planning", "epic_planning", "Work item type is epic.")
    if work_item_type == "feature":
        return _classification("feature", "high", "planning", "feature_planning", "Work item type is feature.")
    if work_item_type in {"story", "user_story"}:
        return _classification("story", "high", "delivery", "story_delivery", "Work item type is story.")
    if work_item_type == "bug":
        return _classification("bug", "high", "bug_fix", "bug_fix", "Work item type is bug.")
    if work_item_type == "spike":
        return _classification("spike", "high", "research", "spike", "Work item type is spike.")
    if work_item_type == "qa_task" or (work_item_type == "task" and _contains_any(lowered, ["qa", "test design", "regression suite", "automation candidate"])):
        return _classification("qa_task", "medium", "quality", "qa_task", "Task is QA-focused.")
    if work_item_type == "ui_task":
        return _classification("ui_task", "high", "design", "ui_task", "Work item type is ui_task.")
    if work_item_type == "task" and ("ui_screen" in surfaces or _contains_any(lowered, ["ui", "screen", "page", "layout", "ux"])):
        return _classification("ui_task", "medium", "design", "ui_task", "Task is UI-focused.")
    if work_item_type == "task":
        return _classification("task", "high", "execution", "task_execution", "Work item type is task.")

    if _contains_any(lowered, ["bug", "fix", "broken", "error", "defect"]):
        return _classification("bug", "medium", "bug_fix", "bug_fix", "Bug language was detected in the work item.")
    if _contains_any(lowered, ["story", "user flow", "acceptance criteria"]):
        return _classification("story", "medium", "delivery", "story_delivery", "Story-oriented wording was detected.")
    return _classification("generic", "low", "delivery", "legacy_delivery", "Work item type was not explicit, so the legacy delivery workflow was used.")


def _classification(
    artifact_type: str,
    confidence: str,
    intent: str,
    recommended_template: str,
    reason: str,
) -> dict[str, str]:
    return {
        "artifact_type": artifact_type,
        "confidence": confidence,
        "intent": intent,
        "recommended_template": recommended_template,
        "workflow_template": recommended_template,
        "reason": reason,
    }


def _normalize_type(value: str) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "userstory": "user_story",
        "user_story": "story",
        "product_backlog_item": "story",
        "qatask": "qa_task",
        "ui": "ui_task",
    }
    return aliases.get(normalized, normalized)


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalized_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip().lower() for value in values if str(value).strip()]
