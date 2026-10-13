"""Audit timeline for governance events."""

from __future__ import annotations

from typing import Any

from .types import normalize_audit_event


class AuditTimeline:
    def record(self, events: list[dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
        stored = normalize_audit_event(event)
        events.append(stored)
        return stored

    def timeline(self, events: list[dict[str, Any]], artifact_id: str = "") -> dict[str, Any]:
        filtered = [event for event in events if not artifact_id or event.get("artifactId") == artifact_id]
        filtered.sort(key=lambda event: str(event.get("when") or ""))
        return {"events": filtered, "count": len(filtered)}
