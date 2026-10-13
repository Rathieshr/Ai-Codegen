"""Template definitions for dynamic pipeline construction."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


TEMPLATES: dict[str, dict[str, Any]] = {
    "legacy_delivery": {
        "name": "legacy_delivery",
        "label": "Legacy Delivery",
        "stages": [
            {"name": "ba", "label": "BA", "role": "Business Analyst", "optional": False, "approval_required": True},
            {"name": "ui", "label": "UI", "role": "App UI", "optional": False, "approval_required": True},
            {"name": "dev", "label": "DEV", "role": "Developer", "optional": False, "approval_required": True},
            {"name": "test", "label": "TEST", "role": "QA", "optional": False, "approval_required": True},
            {"name": "critic", "label": "Critic", "role": "Reviewer", "optional": False, "approval_required": True},
        ],
        "output_types": ["refined_requirement", "execution_packet", "test_cases"],
    },
    "epic_planning": {
        "name": "epic_planning",
        "label": "Epic Planning",
        "stages": [
            {"name": "epic_analysis", "label": "Epic Analysis", "role": "Product", "optional": False, "approval_required": True},
            {"name": "feature_generation", "label": "Feature Generation", "role": "Product", "optional": False, "approval_required": True},
            {"name": "story_generation", "label": "Story Generation", "role": "Product", "optional": False, "approval_required": True},
            {"name": "review", "label": "Review", "role": "Reviewer", "optional": False, "approval_required": True},
        ],
        "output_types": ["features", "stories", "dependencies", "risks"],
    },
    "feature_planning": {
        "name": "feature_planning",
        "label": "Feature Planning",
        "stages": [
            {"name": "feature_analysis", "label": "Feature Analysis", "role": "Product", "optional": False, "approval_required": True},
            {"name": "story_generation", "label": "Story Generation", "role": "Product", "optional": False, "approval_required": True},
            {"name": "review", "label": "Review", "role": "Reviewer", "optional": False, "approval_required": True},
        ],
        "output_types": ["stories", "tasks", "acceptance_criteria"],
    },
    "story_delivery": {
        "name": "story_delivery",
        "label": "Story Delivery",
        "stages": [
            {"name": "ba", "label": "BA", "role": "Business Analyst", "optional": False, "approval_required": True},
            {"name": "ui_optional", "label": "UI Optional", "role": "App UI", "optional": True, "approval_required": True},
            {"name": "task_planning", "label": "Task Planning", "role": "Delivery Lead", "optional": False, "approval_required": True},
            {"name": "test_planning", "label": "Test Planning", "role": "QA", "optional": False, "approval_required": True},
            {"name": "critic", "label": "Critic", "role": "Reviewer", "optional": False, "approval_required": True},
        ],
        "output_types": ["refined_requirement", "ui_handoff", "child_tasks", "test_cases"],
    },
    "task_execution": {
        "name": "task_execution",
        "label": "Task Execution",
        "stages": [
            {"name": "task_analysis", "label": "Task Analysis", "role": "Analyst", "optional": False, "approval_required": True},
            {"name": "dev_packet", "label": "DEV Packet", "role": "Developer", "optional": False, "approval_required": True},
            {"name": "test_checklist", "label": "Test Checklist", "role": "QA", "optional": False, "approval_required": True},
        ],
        "output_types": ["execution_packet", "validation_checklist"],
    },
    "bug_fix": {
        "name": "bug_fix",
        "label": "Bug Fix",
        "stages": [
            {"name": "bug_analysis", "label": "Bug Analysis", "role": "Analyst", "optional": False, "approval_required": True},
            {"name": "impact_analysis", "label": "Impact Analysis", "role": "Developer", "optional": False, "approval_required": True},
            {"name": "fix_packet", "label": "Fix Packet", "role": "Developer", "optional": False, "approval_required": True},
            {"name": "regression_tests", "label": "Regression Tests", "role": "QA", "optional": False, "approval_required": True},
        ],
        "output_types": ["bug_fix_packet", "regression_checklist"],
    },
    "qa_task": {
        "name": "qa_task",
        "label": "QA Task",
        "stages": [
            {"name": "test_design", "label": "Test Design", "role": "QA", "optional": False, "approval_required": True},
            {"name": "automation_draft_optional", "label": "Automation Draft Optional", "role": "QA", "optional": True, "approval_required": True},
        ],
        "output_types": ["test_cases", "automation_candidates"],
    },
    "ui_task": {
        "name": "ui_task",
        "label": "UI Task",
        "stages": [
            {"name": "ui_plan", "label": "UI Plan", "role": "App UI", "optional": False, "approval_required": True},
            {"name": "ui_handoff", "label": "UI Handoff", "role": "App UI", "optional": False, "approval_required": True},
        ],
        "output_types": ["ui_structure", "states", "ux_notes"],
    },
    "spike": {
        "name": "spike",
        "label": "Spike",
        "stages": [
            {"name": "research_plan", "label": "Research Plan", "role": "Analyst", "optional": False, "approval_required": True},
            {"name": "findings", "label": "Findings", "role": "Analyst", "optional": False, "approval_required": True},
            {"name": "recommendation", "label": "Recommendation", "role": "Reviewer", "optional": False, "approval_required": True},
        ],
        "output_types": ["investigation_summary", "recommendation"],
    },
}


def get_pipeline_template(template_name: str) -> dict[str, Any]:
    template = TEMPLATES.get(template_name)
    if not template:
        raise ValueError(f"Unknown pipeline template: {template_name}")
    return deepcopy(template)


def list_stage_names(template: dict[str, Any]) -> list[str]:
    return [stage["name"] for stage in template.get("stages", [])]


def stage_metadata_map(template: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["name"]: dict(stage) for stage in template.get("stages", [])}
