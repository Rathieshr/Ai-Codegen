"""Notification service foundation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..events import EventBus, PlatformEventType
from ..shared import JsonListStore
from .types import normalize_notification


class INotificationService(Protocol):
    def create(self, notification: dict[str, Any]) -> dict[str, Any]:
        ...

    def mark_read(self, notification_id: str) -> dict[str, Any] | None:
        ...

    def list_recent(self, unread_only: bool = False, limit: int = 50) -> dict[str, Any]:
        ...


class NotificationService:
    def __init__(self, storage_path: Path, event_bus: EventBus | None = None) -> None:
        self._store = JsonListStore(storage_path)
        self._event_bus = event_bus

    def create(self, notification: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_notification(notification)
        items = self._store.read()
        items.append(normalized)
        self._store.write(items)
        if self._event_bus:
            self._event_bus.publish(
                {
                    "eventType": PlatformEventType.VALIDATION_COMPLETED.value,
                    "source": normalized["source"],
                    "correlationId": normalized["correlationId"],
                    "payload": {
                        "notificationId": normalized["notificationId"],
                        "notificationType": normalized["type"],
                        "notificationEvent": "NotificationCreated",
                    },
                }
            )
        return normalized

    def mark_read(self, notification_id: str) -> dict[str, Any] | None:
        items = self._store.read()
        for index, item in enumerate(items):
            if item.get("notificationId") == notification_id:
                updated = normalize_notification({**item, "readAt": item.get("readAt") or item.get("createdAt")})
                items[index] = updated
                self._store.write(items)
                return updated
        return None

    def list_recent(self, unread_only: bool = False, limit: int = 50) -> dict[str, Any]:
        items = self._store.read()
        filtered = [item for item in items if not unread_only or not item.get("readAt")]
        recent = list(reversed(filtered[-limit:]))
        return {"notifications": recent, "count": len(filtered)}
