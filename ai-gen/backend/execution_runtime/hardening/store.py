"""Persistence for Runtime Hardening benchmark reports."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class RuntimeHardeningStore:
    def __init__(self, path) -> None:
        self.store = JsonMapStore(path)

    def save(self, report: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        values[report["runId"]] = deepcopy(report)
        self.store.write(values)
        return deepcopy(report)

    def get(self, run_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(run_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def latest(self) -> dict[str, Any] | None:
        values = [value for value in self.store.read().values() if isinstance(value, dict)]
        if not values:
            return None
        return deepcopy(max(values, key=lambda value: str(value.get("generatedAt") or "")))
