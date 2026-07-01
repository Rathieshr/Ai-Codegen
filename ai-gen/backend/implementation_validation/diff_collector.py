"""Collect and normalize repository diff input for implementation validation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .models import clean


class DiffCollector:
    """Normalize provided diff payloads, with optional local git fallback."""

    def collect(
        self,
        repository_diff: dict[str, Any] | None = None,
        changed_files: list[Any] | None = None,
        repo_path: str | None = None,
    ) -> dict[str, Any]:
        repository_diff = repository_diff or {}
        supplied = changed_files or repository_diff.get("changed_files") or repository_diff.get("changedFiles") or repository_diff.get("files") or []
        normalized = [self._normalize_file(item) for item in supplied if self._normalize_file(item).get("path")]
        if not normalized and repo_path:
            normalized = self._collect_git_diff(repo_path)
        return {
            "changedFiles": normalized,
            "diffText": clean(repository_diff.get("diff") or repository_diff.get("patch") or ""),
            "source": "provided" if supplied else ("git" if normalized else "none"),
        }

    def _normalize_file(self, item: Any) -> dict[str, Any]:
        if isinstance(item, str):
            return {"path": clean(item), "status": "modified", "diff": "", "additions": 0, "deletions": 0}
        if not isinstance(item, dict):
            return {}
        return {
            "path": clean(item.get("path") or item.get("file") or item.get("filename") or item.get("name")),
            "status": clean(item.get("status") or item.get("changeType") or "modified"),
            "diff": str(item.get("diff") or item.get("patch") or item.get("content") or ""),
            "additions": int(item.get("additions") or item.get("linesAdded") or 0),
            "deletions": int(item.get("deletions") or item.get("linesDeleted") or 0),
        }

    def _collect_git_diff(self, repo_path: str) -> list[dict[str, Any]]:
        path = Path(repo_path)
        if not path.exists():
            return []
        try:
            names = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return [
                {"path": clean(line), "status": "modified", "diff": "", "additions": 0, "deletions": 0}
                for line in names.stdout.splitlines()
                if clean(line)
            ]
        except (OSError, subprocess.SubprocessError):
            return []
