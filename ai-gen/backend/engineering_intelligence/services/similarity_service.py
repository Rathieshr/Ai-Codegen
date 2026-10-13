"""Similarity and reuse projections over already retrieved evidence."""

from __future__ import annotations

from typing import Any, Callable

from ..models import EngineeringContext


class SimilarityService:
    def __init__(
        self,
        requirement_finder: Callable[[EngineeringContext | dict[str, Any]], list[dict[str, Any]]],
        implementation_finder: Callable[[EngineeringContext | dict[str, Any]], list[dict[str, Any]]],
    ) -> None:
        self._requirement_finder = requirement_finder
        self._implementation_finder = implementation_finder

    def find_similar_requirement(
        self, value: EngineeringContext | dict[str, Any],
    ) -> list[dict[str, Any]]:
        return self._requirement_finder(value)

    def find_reusable_implementation(
        self, value: EngineeringContext | dict[str, Any],
    ) -> list[dict[str, Any]]:
        return self._implementation_finder(value)

    findSimilarRequirement = find_similar_requirement
    findReusableImplementation = find_reusable_implementation
