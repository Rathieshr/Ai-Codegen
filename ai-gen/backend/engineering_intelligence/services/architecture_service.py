"""Architecture fact projections over Repository Intelligence."""

from __future__ import annotations

from typing import Any, Callable

from ..models import ArchitectureSummary, RepositorySummary


class ArchitectureService:
    def __init__(
        self,
        analyzer: Callable[[RepositorySummary | dict[str, Any]], ArchitectureSummary],
    ) -> None:
        self._analyzer = analyzer

    def analyze_architecture(
        self, repository: RepositorySummary | dict[str, Any],
    ) -> ArchitectureSummary:
        return self._analyzer(repository)

    def get_architecture_context(
        self, repository: RepositorySummary | dict[str, Any],
    ) -> dict[str, Any]:
        return self.analyze_architecture(repository).__dict__.copy()

    analyzeArchitecture = analyze_architecture
    getArchitectureContext = get_architecture_context
