"""JSON-backed trace repository."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .types import normalize_trace, now_iso


class TraceRepository:
    def __init__(self, storage_path: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._path = storage_path or data_dir / "project_intelligence" / "intelligence_trace.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            traces = payload.get("traces") if isinstance(payload, dict) else []
            return [normalize_trace(trace) for trace in traces if isinstance(trace, dict)]
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, trace: dict[str, Any]) -> dict[str, Any]:
        traces = self.list()
        normalized = normalize_trace(trace)
        traces.append(normalized)
        self._write(traces)
        return normalized

    def replace(self, traces: list[dict[str, Any]]) -> None:
        self._write([normalize_trace(trace) for trace in traces])

    def _write(self, traces: list[dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps({"schemaVersion": "intelligence-trace-v1", "traces": traces, "updatedAt": now_iso()}, indent=2),
            encoding="utf-8",
        )
