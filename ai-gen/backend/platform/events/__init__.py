"""Platform event bus foundation."""

from .service import EventBus, EventHandlerRegistry, IEventBus, IEventHandler
from .types import PlatformEventType, normalize_platform_event

__all__ = [
    "EventBus",
    "EventHandlerRegistry",
    "IEventBus",
    "IEventHandler",
    "PlatformEventType",
    "normalize_platform_event",
]
