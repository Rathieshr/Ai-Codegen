"""Audit trail service for platform foundation changes."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..shared import JsonListStore
from .types import normalize_audit_event


class IAuditService(Protocol):
    def record(self, event: dict) -> dict:
        ...

    def by_target(self, target_type: str, target_id: str) -> dict:
        ...

    def by_actor(self, actor: str) -> dict:
        ...

    def by_correlation(self, correlation_id: str) -> dict:
        ...

    def list_recent(self, limit: int = 50) -> dict:
        ...


class AuditService:
    def __init__(self, storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)

    def record(self, event: dict) -> dict:
        normalized = normalize_audit_event(event)
        items = self._store.read()
        items.append(normalized)
        self._store.write(items)
        return normalized

    def by_target(self, target_type: str, target_id: str) -> dict:
        items = [
            item
            for item in self._store.read()
            if item.get("targetType") == target_type and item.get("targetId") == target_id
        ]
        return {"events": list(reversed(items)), "count": len(items)}

    def by_actor(self, actor: str) -> dict:
        items = [item for item in self._store.read() if item.get("actor") == actor]
        return {"events": list(reversed(items)), "count": len(items)}

    def by_correlation(self, correlation_id: str) -> dict:
        items = [item for item in self._store.read() if item.get("correlationId") == correlation_id]
        return {"events": list(reversed(items)), "count": len(items)}

    def list_recent(self, limit: int = 50) -> dict:
        items = self._store.read()
        return {"events": list(reversed(items[-max(1, limit):])), "count": len(items)}
