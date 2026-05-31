"""Route work items into workflow templates."""

from __future__ import annotations

from typing import Any

from .artifact_classifier import classify_work_item
from .pipeline_templates import get_pipeline_template


def route_work_item_to_template(work_item: dict[str, Any], refinement: dict[str, Any] | None = None) -> tuple[dict[str, str], dict[str, Any]]:
    classification = classify_work_item(work_item, refinement=refinement)
    template = get_pipeline_template(classification["recommended_template"])
    return classification, template
