"""Task planning helpers for workflow-template pipelines."""

from __future__ import annotations

from typing import Any

from .child_task_planner import generate_child_task_preview
from .work_item_drafts import build_child_task_drafts_for_story


def generate_task_plan_preview(
    work_item: dict[str, Any],
    *,
    source_stage: str,
    title_seed: str,
    include_ui: bool,
    fields: list[str],
    variants: list[str],
    stage_output: dict[str, Any] | None = None,
    refinement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refinement = refinement or {}
    preview_source = stage_output or {"summary": title_seed, "fields": fields}
    return {
        "proposed_child_tasks": generate_child_task_preview(work_item, preview_source, refinement),
        "proposed_work_items": build_child_task_drafts_for_story(
            work_item,
            source_stage=source_stage,
            title_seed=title_seed,
            include_ui=include_ui,
            fields=fields,
            variants=variants,
        ),
    }
