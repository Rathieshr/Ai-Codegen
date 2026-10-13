"""Persistent repository for runtime trace projections."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class RuntimeTraceRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save(self, trace: dict[str, Any]) -> dict[str, Any]:
        traces = self.store.read()
        traces[trace["traceId"]] = deepcopy(trace)
        self.store.write(traces)
        return deepcopy(trace)

    def get(self, trace_id: str) -> dict[str, Any] | None:
        traces = self.store.read()
        direct = traces.get(trace_id)
        if isinstance(direct, dict):
            return deepcopy(direct)
        for trace in traces.values():
            if isinstance(trace, dict) and trace_id in {
                trace.get("sessionId"),
                trace.get("correlationId"),
            }:
                return deepcopy(trace)
        return None

    def list(self) -> list[dict[str, Any]]:
        values = [deepcopy(value) for value in self.store.read().values() if isinstance(value, dict)]
        return sorted(values, key=lambda value: str(value.get("updatedAt") or ""), reverse=True)
