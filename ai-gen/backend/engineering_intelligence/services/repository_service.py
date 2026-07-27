"""Repository Intelligence adapter. Repository scanning remains provider-owned."""

from __future__ import annotations

from typing import Any, Callable

from ..models import RepositorySummary


class RepositoryService:
    def __init__(
        self,
        analyzer: Callable[[dict[str, Any]], RepositorySummary],
        repository_provider: Any | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._provider = repository_provider

    def analyze_repository(self, requirement: dict[str, Any]) -> RepositorySummary:
        return self._analyzer(requirement)

    def get_repository_summary(self, requirement: dict[str, Any]) -> RepositorySummary:
        return self.analyze_repository(requirement)

    def find_relevant_modules(self, requirement: dict[str, Any]) -> list[str]:
        summary = self.analyze_repository(requirement)
        return list(summary.affectedModules or summary.modules)

    def find_relevant_files(self, requirement: dict[str, Any]) -> list[dict[str, Any]]:
        return list(self.analyze_repository(requirement).files)

    def find_technology_stack(self, requirement: dict[str, Any]) -> dict[str, list[str]]:
        summary = self.analyze_repository(requirement)
        repository = (
            self._provider.get_repository(summary.repositoryId)
            if self._provider and summary.repositoryId
            else {}
        ) or {}
        stack = (repository.get("metadata") or {}).get("technologyStack") or {}
        return {
            str(key): [str(item) for item in value]
            for key, value in stack.items()
            if isinstance(value, list)
        }

    analyzeRepository = analyze_repository
    getRepositorySummary = get_repository_summary
    findRelevantModules = find_relevant_modules
    findRelevantFiles = find_relevant_files
    findTechnologyStack = find_technology_stack
