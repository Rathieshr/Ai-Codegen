from __future__ import annotations

from typing import Any

from .planning_context_builder import PlanningContextBuilder


class PlanningEngine:
    def __init__(self) -> None:
        self.builder = PlanningContextBuilder()

    def build_planning_context(self, work_item: dict[str, Any], parent_work_item: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.builder.build(work_item, parent_work_item, options)


def build_planning_context(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return PlanningEngine().build_planning_context(work_item, parent_work_item, options)


def buildPlanningContext(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_planning_context(work_item, parent_work_item, options)
