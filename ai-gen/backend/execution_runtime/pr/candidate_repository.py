"""Immutable Pull Request candidate persistence."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class PRCandidateRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save(self, candidate: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        candidate_id = str(candidate["candidateId"])
        existing = values.get(candidate_id)
        if isinstance(existing, dict):
            left = {key: value for key, value in existing.items() if key != "generatedAt"}
            right = {key: value for key, value in candidate.items() if key != "generatedAt"}
            if left != right:
                raise ValueError("Pull Request candidate identity collision detected.")
            return deepcopy(existing)
        values[candidate_id] = deepcopy(candidate)
        self.store.write(values)
        return deepcopy(candidate)

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(candidate_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def list(self) -> list[dict[str, Any]]:
        values = [deepcopy(item) for item in self.store.read().values() if isinstance(item, dict)]
        return sorted(values, key=lambda item: str(item.get("generatedAt") or ""), reverse=True)
