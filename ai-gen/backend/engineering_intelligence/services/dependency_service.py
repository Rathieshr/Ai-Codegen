"""Dependency fact projections over the Engineering Graph."""

from __future__ import annotations

from typing import Any, Callable

from ..models import DependencySummary, RepositorySummary


class DependencyService:
    def __init__(
        self,
        analyzer: Callable[
            [dict[str, Any], RepositorySummary | dict[str, Any]], DependencySummary
        ],
    ) -> None:
        self._analyzer = analyzer

    def analyze_dependencies(
        self,
        requirement: dict[str, Any],
        repository: RepositorySummary | dict[str, Any],
    ) -> DependencySummary:
        return self._analyzer(requirement, repository)

    def find_affected_modules(
        self,
        requirement: dict[str, Any],
        repository: RepositorySummary | dict[str, Any],
    ) -> list[str]:
        value = repository if isinstance(repository, dict) else repository.__dict__
        affected = value.get("affectedModules") or value.get("modules") or []
        return [str(item) for item in affected if str(item).strip()]

    analyzeDependencies = analyze_dependencies
    findAffectedModules = find_affected_modules
