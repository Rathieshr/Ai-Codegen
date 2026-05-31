"""Workflow template routing for ai-gen pipelines."""

from .artifact_classifier import classify_work_item
from .child_task_planner import generate_child_task_preview
from .pipeline_templates import get_pipeline_template, list_stage_names
from .stage_registry import run_stage_critic, run_stage_output
from .workflow_router import route_work_item_to_template

__all__ = [
    "classify_work_item",
    "generate_child_task_preview",
    "get_pipeline_template",
    "list_stage_names",
    "route_work_item_to_template",
    "run_stage_output",
    "run_stage_critic",
]
