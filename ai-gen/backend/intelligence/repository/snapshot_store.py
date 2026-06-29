from __future__ import annotations

import json
import os
from pathlib import Path

from .repository_snapshot import RepositorySnapshot


class RepositorySnapshotStore:
    """JSON history store. Keeps every snapshot version for drift and audit."""

    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parents[3] / "data")))
            root = data_dir / "project_intelligence" / "repository_snapshots"
        self.root = Path(root)

    def list_snapshots(self, repository_id: str) -> list[RepositorySnapshot]:
        folder = self._folder(repository_id)
        snapshots = []
        for path in sorted(folder.glob("snapshot_v*.json")):
            snapshots.append(RepositorySnapshot.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return sorted(snapshots, key=lambda snapshot: snapshot.scan_version)

    def latest(self, repository_id: str) -> RepositorySnapshot | None:
        snapshots = self.list_snapshots(repository_id)
        return snapshots[-1] if snapshots else None

    def next_version(self, repository_id: str) -> int:
        latest = self.latest(repository_id)
        return (latest.scan_version + 1) if latest else 1

    def save(self, snapshot: RepositorySnapshot) -> dict:
        folder = self._folder(snapshot.repository_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"snapshot_v{snapshot.scan_version}.json"
        path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        latest_path = folder / "latest.json"
        latest_path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return {"path": str(path), "latest": str(latest_path), "scanVersion": snapshot.scan_version}

    def _folder(self, repository_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in repository_id or "repository")
        return self.root / safe
