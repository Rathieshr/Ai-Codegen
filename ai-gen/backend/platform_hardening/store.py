"""Persistent run and trace storage for Milestone 3.5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.platform.shared import JsonListStore


class HardeningRunStore:
    def __init__(self, storage_root: Path) -> None:
        self.runs = JsonListStore(storage_root / "regression_runs.json")
        self.traces = JsonListStore(storage_root / "run_traces.json")

    def save_run(self, run: dict[str, Any]) -> dict[str, Any]:
        items = self.runs.read()
        items = [item for item in items if item.get("runId") != run.get("runId")]
        items.append(run)
        self.runs.write(items)
        return run

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(reversed(self.runs.read()[-max(1, limit):]))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return next((item for item in self.runs.read() if item.get("runId") == run_id), None)

    def append_trace(self, event: dict[str, Any]) -> dict[str, Any]:
        items = self.traces.read()
        items.append(event)
        self.traces.write(items)
        return event

    def trace(self, correlation_id: str) -> list[dict[str, Any]]:
        events = [item for item in self.traces.read() if item.get("correlationId") == correlation_id]
        return sorted(events, key=lambda item: (item.get("sequence", 0), item.get("timestamp", "")))
