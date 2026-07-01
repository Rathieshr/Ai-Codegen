"""Resolve PR diffs into Implementation Validation changed-file input."""

from __future__ import annotations

from typing import Any

from backend.implementation_validation.diff_collector import DiffCollector


class PRDiffResolver:
    def __init__(self) -> None:
        self.collector = DiffCollector()

    def resolve(self, pull_request: dict[str, Any] | None = None, repository_diff: dict[str, Any] | None = None, changed_files: list[Any] | None = None) -> dict[str, Any]:
        pull_request = pull_request or {}
        diff = repository_diff or pull_request.get("repository_diff") or pull_request.get("repositoryDiff") or {}
        files = changed_files or pull_request.get("changed_files") or pull_request.get("changedFiles") or []
        return self.collector.collect(diff, files)
