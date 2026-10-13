"""Small in-memory cache for immutable reasoning results."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


class ReasoningCache:
    def __init__(self) -> None:
        self._values: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._values.get(key)
            return deepcopy(value) if value is not None else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._values[key] = deepcopy(value)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
