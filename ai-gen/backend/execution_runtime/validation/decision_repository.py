"""Persistence for immutable Validation Trigger decisions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class ValidationTriggerRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save(self, decision: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        decision_id = str(decision["decisionId"])
        existing = values.get(decision_id)
        if isinstance(existing, dict):
            left = {key: value for key, value in existing.items() if key != "decidedAt"}
            right = {key: value for key, value in decision.items() if key != "decidedAt"}
            if left != right:
                raise ValueError("Validation Trigger decision identity collision detected.")
            return deepcopy(existing)
        values[decision_id] = deepcopy(decision)
        self.store.write(values)
        return deepcopy(decision)

    def get(self, decision_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(decision_id)
        return deepcopy(value) if isinstance(value, dict) else None
