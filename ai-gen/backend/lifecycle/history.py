"""Lifecycle history utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class LifecycleHistory:
    def event(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        event_type: str,
        from_state: str = "",
        to_state: str = "",
        actor: str = "",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "eventId": f"lifecycle_{uuid4().hex[:12]}",
            "artifactId": artifact_id,
            "artifactType": artifact_type,
            "eventType": event_type,
            "fromState": from_state,
            "toState": to_state,
            "actor": actor or "HEI",
            "reason": reason,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def append(self, history: list[dict[str, Any]], event: dict[str, Any]) -> list[dict[str, Any]]:
        return [*history, event]
