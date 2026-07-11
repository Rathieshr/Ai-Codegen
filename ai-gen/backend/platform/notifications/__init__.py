"""Platform notification foundation."""

from .service import INotificationService, NotificationService
from .types import NotificationSeverity, normalize_notification

__all__ = [
    "INotificationService",
    "NotificationService",
    "NotificationSeverity",
    "normalize_notification",
]
