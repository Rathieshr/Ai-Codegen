from __future__ import annotations

from typing import Any

from .planning_context import PlanningLineage


def build_lineage(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None) -> PlanningLineage:
    parent = parent_work_item or work_item
    parent_type = _type(parent)
    work_type = _type(work_item)
    return PlanningLineage(
        derived_from_id=_id(parent),
        derived_from_type=parent_type,
        derived_from_title=_title(parent),
        derivation_rule=_rule(parent_type, work_type),
    )


def _rule(parent_type: str, work_type: str) -> str:
    if parent_type == "Epic" and work_type == "Feature":
        return "Epic → Feature: derive only from Epic business objective, expected outcomes, intent, relevant capabilities, and knowledge."
    if parent_type == "Feature" and work_type == "Story":
        return "Feature → Story: derive only from selected Feature capability, business value, acceptance areas, personas, flows, and modules."
    if parent_type == "Story" and work_type == "Task":
        return "Story → Task: derive only from Story description, acceptance criteria, selected modules, selected flows, repository artifacts, and standards."
    if parent_type == "Task" or work_type == "Task":
        return "Task → Execution: derive only from selected Task, parent Story, acceptance criteria, selected modules, selected flows, and repository-ranked files."
    if work_type == "Epic":
        return "Epic refinement: derive from the Epic work item intent and relevant knowledge only."
    return f"{parent_type} → {work_type}: derive from parent-supported planning context only."


def _id(item: dict[str, Any]) -> int | str | None:
    return item.get("id") or item.get("workItemId") or item.get("work_item_id")


def _type(item: dict[str, Any]) -> str:
    return str(item.get("type") or item.get("workItemType") or item.get("work_item_type") or "Task").replace("User Story", "Story")


def _title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("System.Title") or "Work Item").strip()
