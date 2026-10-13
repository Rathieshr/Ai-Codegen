"""Persistence for Azure DevOps hardening reports."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.platform.shared import JsonMapStore


class AzureDevOpsHardeningStore:
    def __init__(self, storage_root: Path) -> None:
        storage_root.mkdir(parents=True, exist_ok=True)
        self.store = JsonMapStore(storage_root / "phase6_hardening_runs.json")

    def save(self, report: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        values[report["runId"]] = deepcopy(report)
        self.store.write(values)
        return deepcopy(report)

    def get(self, run_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(run_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        values = [value for value in self.store.read().values() if isinstance(value, dict)]
        return [deepcopy(value) for value in sorted(values, key=lambda item: str(item.get("generatedAt") or ""), reverse=True)[:max(1, limit)]]

    def latest(self) -> dict[str, Any] | None:
        values = self.list(1)
        return values[0] if values else None
