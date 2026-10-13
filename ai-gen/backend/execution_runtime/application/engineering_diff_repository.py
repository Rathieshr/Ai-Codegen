"""Persistence for immutable semantic Engineering Diff results."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class EngineeringDiffRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save(self, engineering_diff: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        diff_id = str(engineering_diff["diffId"])
        existing = values.get(diff_id)
        if isinstance(existing, dict) and existing != engineering_diff:
            raise ValueError("Engineering Diff is immutable and cannot be overwritten.")
        values[diff_id] = deepcopy(engineering_diff)
        self.store.write(values)
        return deepcopy(engineering_diff)

    def get(self, diff_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(diff_id)
        return deepcopy(value) if isinstance(value, dict) else None
