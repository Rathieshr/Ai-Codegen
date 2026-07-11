"""Activity log service for future portal feeds."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..shared import JsonListStore
from .types import normalize_activity_log_entry


class IActivityLogService(Protocol):
    def add_activity(self, entry: dict) -> dict:
        ...

    def list_recent(self, limit: int = 50, **filters: str) -> dict:
        ...


class ActivityLogService:
    def __init__(self, storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)

    def add_activity(self, entry: dict) -> dict:
        normalized = normalize_activity_log_entry(entry)
        items = self._store.read()
        items.append(normalized)
        self._store.write(items)
        return normalized

    def list_recent(self, limit: int = 50, **filters: str) -> dict:
        items = self._store.read()
        filtered = [
            item
            for item in items
            if all(not value or item.get(key) == value for key, value in filters.items())
        ]
        recent = list(reversed(filtered[-limit:]))
        return {"activity": recent, "count": len(filtered)}
