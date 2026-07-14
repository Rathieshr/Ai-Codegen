"""Connection persistence that retains references but never credential values."""

from __future__ import annotations

from threading import RLock

from backend.platform.shared import JsonMapStore

from ..domain import AzureDevOpsConnection


class AzureDevOpsConnectionRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self._store = store
        self._lock = RLock()

    def save(self, connection: AzureDevOpsConnection) -> AzureDevOpsConnection:
        with self._lock:
            records = self._store.read()
            records[connection.connection_id] = connection.to_storage_dict()
            self._store.write(records)
        return connection

    def get(self, connection_id: str) -> AzureDevOpsConnection | None:
        value = self._store.read().get(connection_id)
        return AzureDevOpsConnection.from_dict(value) if isinstance(value, dict) else None

    def list(self) -> list[AzureDevOpsConnection]:
        return [AzureDevOpsConnection.from_dict(item) for item in self._store.read().values() if isinstance(item, dict)]

    def find_duplicate(self, organization_url: str, project_id: str = "") -> AzureDevOpsConnection | None:
        normalized = organization_url.rstrip("/").lower()
        return next((item for item in self.list() if item.organization_url.lower() == normalized and item.project_id == project_id), None)
