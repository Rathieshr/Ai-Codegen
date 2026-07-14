"""Persistence for immutable QA Execution Plans."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class QAExecutionPlanRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save(self, plan: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        plan_id = str(plan["planId"])
        existing = values.get(plan_id)
        if isinstance(existing, dict):
            left = {key: value for key, value in existing.items() if key != "generatedAt"}
            right = {key: value for key, value in plan.items() if key != "generatedAt"}
            if left != right:
                raise ValueError("QA Execution Plan identity collision detected.")
            return deepcopy(existing)
        values[plan_id] = deepcopy(plan)
        self.store.write(values)
        return deepcopy(plan)

    def get(self, plan_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(plan_id)
        return deepcopy(value) if isinstance(value, dict) else None
