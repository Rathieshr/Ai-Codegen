"""Notification models for the platform foundation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..shared import OperationSource, clean, enum_value, generated_id, now_iso


class NotificationSeverity(str, Enum):
    INFO = "Info"
    SUCCESS = "Success"
    WARNING = "Warning"
    ERROR = "Error"
    CRITICAL = "Critical"


def normalize_notification(notification: dict[str, Any]) -> dict[str, Any]:
    return {
        "notificationId": clean(notification.get("notificationId") or notification.get("id")) or generated_id("notification"),
        "type": clean(notification.get("type")) or "PlatformNotification",
        "title": clean(notification.get("title")) or "Platform notification",
        "message": clean(notification.get("message")),
        "severity": enum_value(notification.get("severity"), NotificationSeverity, NotificationSeverity.INFO),
        "source": enum_value(notification.get("source"), OperationSource, OperationSource.API),
        "correlationId": clean(notification.get("correlationId")) or generated_id("corr"),
        "targetUserId": clean(notification.get("targetUserId")),
        "targetRole": clean(notification.get("targetRole")),
        "createdAt": clean(notification.get("createdAt")) or now_iso(),
        "readAt": clean(notification.get("readAt")),
    }
