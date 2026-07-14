"""Persistent idempotency and partial-execution state."""

from __future__ import annotations

from threading import RLock
from typing import Any

from backend.platform.shared import JsonMapStore


class AutomationExecutionStore:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store
        self._lock = RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        value = self.store.read().get(key)
        return value if isinstance(value, dict) else None

    def save(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            records = self.store.read(); records[key] = value; self.store.write(records)
        return value
