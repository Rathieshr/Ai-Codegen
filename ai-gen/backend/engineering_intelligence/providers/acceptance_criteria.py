"""Compatibility adapter for HEI's stabilized acceptance-criteria capability."""

from __future__ import annotations

from typing import Any


class AcceptanceCriteriaProvider:
    def __init__(self, project_intelligence: Any) -> None:
        self._project_intelligence = project_intelligence

    def generate(
        self,
        requirement: dict[str, Any],
        project_profile: dict[str, Any] | None = None,
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return dict(self._project_intelligence.generate_requirement_acceptance_criteria(
            requirement,
            project_profile or self._project_intelligence.get_profile() or {},
            options=options or {},
        ))
