"""Single workflow entry point for Engineering Intelligence."""

from __future__ import annotations

from typing import Any

from ..models import EngineeringContext


class IntelligenceOrchestrator:
    def __init__(self, intelligence: Any, context_builder: Any) -> None:
        self._intelligence = intelligence
        self._context_builder = context_builder

    def build_requirement_context(
        self, requirement: dict[str, Any], *, correlation_id: str = "",
    ) -> dict[str, Any]:
        result = self._intelligence.generate_planning_context(
            requirement, correlation_id=correlation_id,
        )
        return self._context_builder.build_optimized_context(result["engineeringContext"])

    def build_planning_context(
        self, requirement: dict[str, Any], *, correlation_id: str = "",
    ) -> dict[str, Any]:
        return self._intelligence.generate_planning_context(
            requirement, correlation_id=correlation_id,
        )

    def build_execution_context(
        self, value: EngineeringContext | dict[str, Any], **_kwargs: Any,
    ) -> dict[str, Any]:
        return self._intelligence.execution_context(value)

    def build_validation_context(
        self, value: EngineeringContext | dict[str, Any], **_kwargs: Any,
    ) -> dict[str, Any]:
        return self._intelligence.validation_context(value)

    buildRequirementContext = build_requirement_context
    buildPlanningContext = build_planning_context
    buildExecutionContext = build_execution_context
    buildValidationContext = build_validation_context
