"""Simple in-process event bus for agent workflows."""

from __future__ import annotations

from typing import Any

from .types import normalize_event


class AgentEventBus:
    def publish(self, events: list[dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_event(event)
        events.append(normalized)
        return normalized

    def list_events(self, events: list[dict[str, Any]], event_type: str = "") -> dict[str, Any]:
        filtered = [event for event in events if not event_type or event.get("eventType") == event_type]
        return {"events": filtered, "count": len(filtered)}
