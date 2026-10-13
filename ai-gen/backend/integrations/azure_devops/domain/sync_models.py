"""Synchronization domain models for the Azure DevOps integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .models import now_iso


class AzureDevOpsSyncType(str, Enum):
    INITIAL_FULL = "InitialFullSync"
    INCREMENTAL = "IncrementalSync"
    WEBHOOK = "WebhookSync"
    SCHEDULED_RECONCILIATION = "ScheduledReconciliation"
    MANUAL = "ManualSync"


class AzureDevOpsSyncStatus(str, Enum):
    QUEUED = "Queued"
    RUNNING = "Running"
    COMPLETED = "Completed"
    PARTIAL = "Partial"
    FAILED = "Failed"


@dataclass
class AzureDevOpsSync:
    sync_id: str
    connection_id: str
    project_id: str
    sync_type: str
    status: str = AzureDevOpsSyncStatus.QUEUED.value
    started_at: str = ""
    completed_at: str = ""
    cursor: str = ""
    items_read: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    correlation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {_camel(key): item for key, item in value.items()}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AzureDevOpsSync":
        return cls(
            sync_id=str(value.get("syncId") or ""),
            connection_id=str(value.get("connectionId") or ""),
            project_id=str(value.get("projectId") or ""),
            sync_type=str(value.get("syncType") or AzureDevOpsSyncType.INCREMENTAL.value),
            status=str(value.get("status") or AzureDevOpsSyncStatus.QUEUED.value),
            started_at=str(value.get("startedAt") or ""),
            completed_at=str(value.get("completedAt") or ""),
            cursor=str(value.get("cursor") or ""),
            items_read=int(value.get("itemsRead") or 0),
            items_created=int(value.get("itemsCreated") or 0),
            items_updated=int(value.get("itemsUpdated") or 0),
            items_deleted=int(value.get("itemsDeleted") or 0),
            warnings=list(value.get("warnings") or []),
            error=str(value.get("error") or ""),
            correlation_id=str(value.get("correlationId") or ""),
        )


@dataclass
class AzureDevOpsMapping:
    mapping_id: str
    mapping_type: str
    hei_id: str
    external_id: str
    connection_id: str
    project_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {_camel(key): item for key, item in asdict(self).items()}


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(item.title() for item in tail)
