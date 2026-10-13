"""In-memory replaceable platform event bus."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..shared import JsonListStore
from .types import normalize_platform_event


class IEventHandler(Protocol):
    def handle(self, event: dict[str, Any]) -> None:
        ...


class IEventBus(Protocol):
    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        ...

    def list_recent(self, event_type: str = "", limit: int = 50) -> dict[str, Any]:
        ...


class EventHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[IEventHandler]] = {}

    def subscribe(self, event_type: str, handler: IEventHandler) -> None:
        self._handlers.setdefault(event_type or "*", []).append(handler)

    def handlers_for(self, event_type: str) -> list[IEventHandler]:
        return [*self._handlers.get(event_type, []), *self._handlers.get("*", [])]


class EventBus:
    def __init__(
        self,
        storage_path: Path,
        registry: EventHandlerRegistry | None = None,
        activity_logger: Any | None = None,
    ) -> None:
        self._store = JsonListStore(storage_path)
        self._registry = registry or EventHandlerRegistry()
        self._activity_logger = activity_logger

    @property
    def registry(self) -> EventHandlerRegistry:
        return self._registry

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_platform_event(event)
        events = self._store.read()
        events.append(normalized)
        self._store.write(events)
        if self._activity_logger:
            self._activity_logger.add_activity(
                {
                    "activityType": "PlatformEvent",
                    "title": normalized["eventType"],
                    "description": f"Platform event published from {normalized['source']}.",
                    "source": normalized["source"],
                    "projectId": normalized.get("projectId"),
                    "repositoryId": normalized.get("repositoryId"),
                    "workItemId": normalized.get("workItemId"),
                    "correlationId": normalized["correlationId"],
                    "metadata": {"payload": normalized.get("payload", {})},
                }
            )
        for handler in self._registry.handlers_for(normalized["eventType"]):
            handler.handle(normalized)
        return normalized

    def list_recent(self, event_type: str = "", limit: int = 50) -> dict[str, Any]:
        events = self._store.read()
        filtered = [item for item in events if not event_type or item.get("eventType") == event_type]
        recent = list(reversed(filtered[-limit:]))
        return {"events": recent, "count": len(filtered)}
