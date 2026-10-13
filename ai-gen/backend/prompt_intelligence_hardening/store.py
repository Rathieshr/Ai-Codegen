"""Persistence for Prompt Intelligence hardening runs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.platform.shared import JsonMapStore


class PromptHardeningStore:
    def __init__(self, storage_root: Path) -> None:
        self.store = JsonMapStore(storage_root / "prompt_intelligence_runs.json")

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
        value = max(values, key=lambda item: str(item.get("generatedAt") or ""), default=None)
        return deepcopy(value) if value else None
