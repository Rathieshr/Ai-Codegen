"""Persistence for Engineering Memory candidate review records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class MemoryCandidateRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save_many(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        values = self.store.read()
        for candidate in candidates:
            candidate_id = str(candidate["candidateId"])
            existing = values.get(candidate_id)
            if isinstance(existing, dict) and existing.get("approvalStatus") in {"Approved", "Rejected"}:
                continue
            values[candidate_id] = deepcopy(candidate)
        self.store.write(values)
        return [deepcopy(values[str(candidate["candidateId"])]) for candidate in candidates]

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(candidate_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def list(self, project_id: str = "") -> list[dict[str, Any]]:
        values = [deepcopy(item) for item in self.store.read().values() if isinstance(item, dict)]
        if project_id:
            values = [item for item in values if (item.get("projectScope") or {}).get("projectId") == project_id]
        return sorted(values, key=lambda item: str(item.get("createdAt") or ""), reverse=True)

    def update(self, candidate: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        candidate_id = str(candidate["candidateId"])
        if candidate_id not in values:
            raise ValueError("Engineering Memory candidate not found.")
        values[candidate_id] = deepcopy(candidate)
        self.store.write(values)
        return deepcopy(candidate)
