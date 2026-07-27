"""Privacy-aware telemetry for reasoning executions."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


class ReasoningTelemetryStore:
    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []
        self._lock = RLock()

    def record(self, value: dict[str, Any]) -> None:
        with self._lock:
            self._records.append(deepcopy(value))

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._records)
