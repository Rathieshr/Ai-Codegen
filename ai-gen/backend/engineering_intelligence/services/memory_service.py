"""Engineering Memory adapter; only approved memory is provider-owned and queried."""

from __future__ import annotations

from typing import Any, Callable

from ..models import EngineeringMemorySummary


class MemoryService:
    def __init__(
        self,
        searcher: Callable[[dict[str, Any]], EngineeringMemorySummary],
        memory_provider: Any | None = None,
    ) -> None:
        self._searcher = searcher
        self._provider = memory_provider

    def search_memory(self, requirement: dict[str, Any]) -> EngineeringMemorySummary:
        return self._searcher(requirement)

    def save_insight(self, insight: dict[str, Any]) -> dict[str, Any]:
        if not self._provider:
            raise RuntimeError("Engineering Memory provider is not configured.")
        writer = getattr(self._provider, "create_candidate", None) or getattr(
            self._provider, "store_candidate", None
        )
        if not callable(writer):
            raise RuntimeError("Engineering Memory provider does not expose candidate storage.")
        return dict(writer(insight))

    def find_lessons_learned(self, requirement: dict[str, Any]) -> list[dict[str, Any]]:
        return list(self.search_memory(requirement).lessonsLearned)

    searchMemory = search_memory
    saveInsight = save_insight
    findLessonsLearned = find_lessons_learned
