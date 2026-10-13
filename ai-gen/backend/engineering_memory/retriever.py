"""Specialized Engineering Memory retrieval APIs."""

from __future__ import annotations

from typing import Any

from .search import MemorySearch


class MemoryRetriever:
    def __init__(self) -> None:
        self.searcher = MemorySearch()

    def find_relevant_memory(self, memories: list[dict[str, Any]], query: dict[str, Any]) -> dict[str, Any]:
        return self.searcher.search(memories, query)

    def find_patterns(self, memories: list[dict[str, Any]], query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.searcher.search(memories, {**(query or {}), "category": "Pattern Memory"})

    def find_architecture(self, memories: list[dict[str, Any]], query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.searcher.search(memories, {**(query or {}), "architecture": True})

    def find_planning_history(self, memories: list[dict[str, Any]], query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.searcher.search(memories, {**(query or {}), "category": "Planning Memory"})

    def find_execution_history(self, memories: list[dict[str, Any]], query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.searcher.search(memories, {**(query or {}), "category": "Execution Memory"})

    def find_lessons(self, memories: list[dict[str, Any]], query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.searcher.search(memories, {**(query or {}), "category": "Lessons Learned"})

    def find_reusable_stories(self, memories: list[dict[str, Any]], query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.searcher.search(memories, {**(query or {}), "category": "Planning Memory", "artifactType": "Story"})
