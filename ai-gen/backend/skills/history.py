"""Persistent history for Engineering Skill execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class SkillHistory:
    def __init__(self, storage_path: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._storage_path = storage_path or data_dir / "project_intelligence" / "engineering_skill_history.json"
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        payload = self._read()
        return payload.get("events", [])

    def record(self, event: dict[str, Any]) -> None:
        payload = self._read()
        events = payload.get("events", [])
        events.append(event)
        self._write({"events": events[-200:]})

    def recent_for_skill(self, skill_id: str) -> list[dict[str, Any]]:
        return [event for event in self.list() if event.get("skillId") == skill_id][-20:]

    def _read(self) -> dict[str, Any]:
        if not self._storage_path.exists():
            return {"events": []}
        try:
            return json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"events": []}

    def _write(self, payload: dict[str, Any]) -> None:
        self._storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
