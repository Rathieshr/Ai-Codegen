"""Persistence for Azure DevOps PR intelligence reports and comment approvals."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from backend.platform.shared import JsonMapStore


class PullRequestIntelligenceRepository:
    def __init__(self, reports: JsonMapStore, comments: JsonMapStore, receipts: JsonMapStore) -> None:
        self.reports, self.comments, self.receipts = reports, comments, receipts
        self._lock = RLock()

    def save_report(self, report: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            values = self.reports.read()
            values[_key(report.get("projectId"), report.get("pullRequestId"))] = deepcopy(report)
            self.reports.write(values)
        return deepcopy(report)

    def get_report(self, pull_request_id: str, project_id: str = "") -> dict[str, Any] | None:
        values = self.reports.read()
        if project_id:
            value = values.get(_key(project_id, pull_request_id))
            return deepcopy(value) if isinstance(value, dict) else None
        value = next((item for key, item in values.items() if key.endswith(f":{pull_request_id}") and isinstance(item, dict)), None)
        return deepcopy(value) if value else None

    def save_comment(self, preview: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            values = self.comments.read(); values[str(preview["commentPreviewId"])] = deepcopy(preview); self.comments.write(values)
        return deepcopy(preview)

    def get_comment(self, preview_id: str) -> dict[str, Any] | None:
        value = self.comments.read().get(preview_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def receipt(self, key: str) -> dict[str, Any] | None:
        value = self.receipts.read().get(key)
        return deepcopy(value) if isinstance(value, dict) else None

    def save_receipt(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            values = self.receipts.read(); values[key] = deepcopy(value); self.receipts.write(values)
        return deepcopy(value)


def _key(project_id: Any, pull_request_id: Any) -> str:
    return f"{project_id or 'unknown'}:{pull_request_id}"
