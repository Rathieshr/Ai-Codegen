"""Persistent centralized cache, cursor, mapping, and webhook receipt stores."""

from __future__ import annotations

import hashlib
import json
from threading import RLock
from typing import Any

from backend.platform.shared import JsonMapStore

from ..domain import AzureDevOpsMapping, AzureDevOpsSync, now_iso


def _sortable(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{int(value):020d}"
    except (TypeError, ValueError):
        return str(value)


class AzureDevOpsSyncRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self._store = store
        self._lock = RLock()

    def save(self, sync: AzureDevOpsSync) -> AzureDevOpsSync:
        with self._lock:
            values = self._store.read()
            values[sync.sync_id] = sync.to_dict()
            self._store.write(values)
        return sync

    def get(self, sync_id: str) -> AzureDevOpsSync | None:
        value = self._store.read().get(sync_id)
        return AzureDevOpsSync.from_dict(value) if isinstance(value, dict) else None

    def history(self, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
        values = [item for item in self._store.read().values() if isinstance(item, dict) and item.get("projectId") == project_id]
        values.sort(key=lambda item: item.get("startedAt") or "", reverse=True)
        return values[:limit]

    def latest(self, project_id: str, *, successful_only: bool = False) -> AzureDevOpsSync | None:
        values = self.history(project_id, 200)
        if successful_only:
            values = [item for item in values if item.get("status") in {"Completed", "Partial"}]
        return AzureDevOpsSync.from_dict(values[0]) if values else None


class AzureDevOpsCacheStore:
    """Stores normalized records keyed by project, collection, and canonical ID."""

    def __init__(self, store: JsonMapStore) -> None:
        self._store = store
        self._lock = RLock()

    def collection(self, project_id: str, name: str) -> dict[str, dict[str, Any]]:
        project = self._store.read().get(project_id, {})
        value = project.get(name, {}) if isinstance(project, dict) else {}
        return value if isinstance(value, dict) else {}

    def upsert(self, project_id: str, name: str, key: str, value: dict[str, Any], *, revision_field: str = "") -> str:
        with self._lock:
            root = self._store.read()
            project = root.setdefault(project_id, {})
            collection = project.setdefault(name, {})
            existing = collection.get(key)
            if existing == value:
                return "unchanged"
            if existing and revision_field:
                old_revision = _sortable(existing.get(revision_field))
                new_revision = _sortable(value.get(revision_field))
                if old_revision and new_revision and new_revision < old_revision:
                    return "out_of_order"
            collection[key] = value
            project["updatedAt"] = now_iso()
            self._store.write(root)
            return "updated" if existing else "created"

    def replace(self, project_id: str, name: str, records: dict[str, dict[str, Any]]) -> tuple[int, int, int]:
        with self._lock:
            root = self._store.read()
            project = root.setdefault(project_id, {})
            existing = project.get(name, {}) if isinstance(project.get(name), dict) else {}
            created = len(set(records) - set(existing))
            deleted = len(set(existing) - set(records))
            updated = sum(1 for key in set(records) & set(existing) if records[key] != existing[key])
            project[name] = records
            project["updatedAt"] = now_iso()
            self._store.write(root)
            return created, updated, deleted

    def delete(self, project_id: str, name: str, key: str) -> bool:
        with self._lock:
            root = self._store.read()
            project = root.get(project_id, {})
            collection = project.get(name, {}) if isinstance(project, dict) else {}
            if key not in collection:
                return False
            del collection[key]
            project["updatedAt"] = now_iso()
            self._store.write(root)
            return True

    def snapshot(self, project_id: str) -> dict[str, Any]:
        value = self._store.read().get(project_id, {})
        return value if isinstance(value, dict) else {}

    def find(self, name: str, key: str, project_id: str = "") -> tuple[str, dict[str, Any]] | None:
        """Find a normalized cached record without calling Azure DevOps."""
        root = self._store.read()
        project_ids = [project_id] if project_id else sorted(root)
        for candidate_project_id in project_ids:
            project = root.get(candidate_project_id, {})
            collection = project.get(name, {}) if isinstance(project, dict) else {}
            value = collection.get(str(key)) if isinstance(collection, dict) else None
            if isinstance(value, dict):
                return str(candidate_project_id), value
        return None

    def project_ids(self) -> list[str]:
        return sorted(str(key) for key in self._store.read())


class AzureDevOpsMappingStore:
    def __init__(self, store: JsonMapStore) -> None:
        self._store = store
        self._lock = RLock()

    def save(self, mapping: AzureDevOpsMapping) -> dict[str, Any]:
        with self._lock:
            values = self._store.read()
            existing = values.get(mapping.mapping_id, {})
            if existing:
                mapping.created_at = str(existing.get("createdAt") or mapping.created_at)
            mapping.updated_at = now_iso()
            values[mapping.mapping_id] = mapping.to_dict()
            self._store.write(values)
        return mapping.to_dict()

    def get(self, mapping_type: str, hei_id: str) -> dict[str, Any] | None:
        return self._store.read().get(f"{mapping_type}:{hei_id}")

    def list(self, project_id: str = "") -> list[dict[str, Any]]:
        values = [item for item in self._store.read().values() if isinstance(item, dict)]
        return [item for item in values if not project_id or item.get("projectId") == project_id]


class AzureDevOpsWebhookReceiptStore:
    def __init__(self, store: JsonMapStore) -> None:
        self._store = store
        self._lock = RLock()

    def event_id(self, payload: dict[str, Any]) -> str:
        supplied = payload.get("id") or payload.get("notificationId") or payload.get("eventId")
        if supplied:
            return str(supplied)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def reserve(self, payload: dict[str, Any]) -> tuple[str, bool]:
        event_id = self.event_id(payload)
        with self._lock:
            values = self._store.read()
            if event_id in values:
                return event_id, False
            values[event_id] = {"eventId": event_id, "status": "Queued", "receivedAt": now_iso()}
            self._store.write(values)
        return event_id, True

    def link(self, event_id: str, sync_id: str) -> None:
        with self._lock:
            values = self._store.read()
            receipt = values.setdefault(event_id, {"eventId": event_id})
            receipt["syncId"] = sync_id
            self._store.write(values)

    def get(self, event_id: str) -> dict[str, Any] | None:
        value = self._store.read().get(event_id)
        return value if isinstance(value, dict) else None

    def complete(self, event_id: str, status: str = "Completed") -> None:
        with self._lock:
            values = self._store.read()
            receipt = values.setdefault(event_id, {"eventId": event_id})
            receipt.update({"status": status, "completedAt": now_iso()})
            self._store.write(values)
