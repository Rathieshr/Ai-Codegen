"""In-memory and optional JSON-backed artifact repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactRepository:
    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self._artifacts: dict[str, dict[str, Any]] = {}
        if self.storage_path and self.storage_path.exists():
            try:
                loaded = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._artifacts = {str(key): value for key, value in loaded.items() if isinstance(value, dict)}
            except (OSError, json.JSONDecodeError):
                self._artifacts = {}

    def save(self, artifact: dict[str, Any]) -> dict[str, Any]:
        artifact_id = str(artifact.get("id") or "")
        if not artifact_id:
            raise ValueError("Artifact id is required.")
        self._artifacts[artifact_id] = dict(artifact)
        self._flush()
        return self._artifacts[artifact_id]

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        artifact = self._artifacts.get(str(artifact_id))
        return dict(artifact) if artifact else None

    def list_by_parent(self, parent_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self._artifacts.values() if str(item.get("parentId") or "") == str(parent_id)]

    def list_by_type(self, artifact_type: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self._artifacts.values() if str(item.get("type") or "") == artifact_type]

    def _flush(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self._artifacts, indent=2, ensure_ascii=False), encoding="utf-8")

