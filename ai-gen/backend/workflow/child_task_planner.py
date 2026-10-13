"""Generate preview child tasks from approved planning outputs."""

from __future__ import annotations

from typing import Any


def generate_child_task_preview(
    work_item: dict[str, Any],
    stage_output: dict[str, Any],
    refinement: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    refinement = refinement or {}
    title = str(work_item.get("title", "")).strip() or str(stage_output.get("summary", "Work item")).strip()
    flows = stage_output.get("flows", []) or refinement.get("base_flows", [])
    fields = stage_output.get("fields", []) or refinement.get("refined_fields", []) or refinement.get("fields", [])
    field_names = [field.get("name", "") if isinstance(field, dict) else str(field) for field in fields]
    child_tasks: list[dict[str, str]] = [
        {
            "type": "task",
            "title": f"Implement {title}",
            "description": f"Build the approved behavior for flows: {', '.join(str(flow) for flow in flows if str(flow).strip()) or 'core workflow'}.",
        },
        {
            "type": "qa_task",
            "title": f"Validate {title}",
            "description": "Prepare and execute the validation and regression checklist for the approved scope.",
        },
    ]
    if _needs_ui(stage_output, refinement):
        child_tasks.insert(
            1,
            {
                "type": "ui_task",
                "title": f"Design {title}",
                "description": f"Define the UI behavior, fields, and states for: {', '.join(name for name in field_names if name) or 'the required interaction flow'}.",
            },
        )
    if _needs_documentation(work_item, stage_output):
        child_tasks.append(
            {
                "type": "task",
                "title": f"Document {title}",
                "description": "Capture release notes, support notes, or developer-facing implementation guidance.",
            }
        )
    return child_tasks


def _needs_ui(stage_output: dict[str, Any], refinement: dict[str, Any]) -> bool:
    surfaces = set(
        str(item).strip().lower()
        for item in list(refinement.get("refined_surfaces", [])) + list(refinement.get("surfaces", []))
        if str(item).strip()
    )
    return bool(stage_output.get("fields")) or "ui_screen" in surfaces or "ui_validation" in surfaces


def _needs_documentation(work_item: dict[str, Any], stage_output: dict[str, Any]) -> bool:
    text = " ".join(
        str(value).lower()
        for value in [
            work_item.get("title", ""),
            work_item.get("description", ""),
            stage_output.get("summary", ""),
        ]
    )
    return any(keyword in text for keyword in ["policy", "workflow", "migration", "rollout"])
