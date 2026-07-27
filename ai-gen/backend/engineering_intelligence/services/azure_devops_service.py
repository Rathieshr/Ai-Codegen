"""Azure DevOps cache adapter; no direct ADO client calls are allowed here."""

from __future__ import annotations

from typing import Any, Callable

from ..models import AzureDevOpsSummary, EngineeringContext


class AzureDevOpsService:
    def __init__(
        self,
        analyzer: Callable[[dict[str, Any]], AzureDevOpsSummary],
        story_finder: Callable[[EngineeringContext | dict[str, Any]], list[dict[str, Any]]],
    ) -> None:
        self._analyzer = analyzer
        self._story_finder = story_finder

    def analyze_project(self, requirement: dict[str, Any]) -> AzureDevOpsSummary:
        return self._analyzer(requirement)

    def find_similar_stories(
        self, value: EngineeringContext | dict[str, Any],
    ) -> list[dict[str, Any]]:
        return self._story_finder(value)

    def find_open_work(self, requirement: dict[str, Any]) -> list[dict[str, Any]]:
        return list(self.analyze_project(requirement).currentDevelopment)

    analyzeProject = analyze_project
    findSimilarStories = find_similar_stories
    findOpenWork = find_open_work
