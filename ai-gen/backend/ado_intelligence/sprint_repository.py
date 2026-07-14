"""Persistence for the latest explainable sprint intelligence report."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from backend.platform.shared import JsonMapStore


class SprintIntelligenceRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store
        self._lock = RLock()

    def save(self, report: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            values = self.store.read()
            values[_key(report["projectId"], report["iterationId"])] = deepcopy(report)
            self.store.write(values)
        return deepcopy(report)

    def get(self, project_id: str, iteration_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(_key(project_id, iteration_id))
        return deepcopy(value) if isinstance(value, dict) else None


def _key(project_id: str, iteration_id: str) -> str:
    return f"{project_id}:{iteration_id}"
