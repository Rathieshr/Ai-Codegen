"""Execution Runtime platform event and activity publisher."""

from __future__ import annotations

from typing import Any


class RuntimeEventPublisher:
    def __init__(self, platform: Any | None = None) -> None:
        self.platform = platform

    def publish(self, event_type: str, session: dict, payload: dict | None = None) -> None:
        if not self.platform:
            return
        result = session.get("result") if isinstance(session.get("result"), dict) else {}
        self.platform.events.publish({
            "eventType": event_type,
            "source": "ExecutionRuntime",
            "correlationId": session["correlationId"],
            "repositoryId": (session.get("runtimeContext") or {}).get("repositoryId"),
            "payload": {
                "sessionId": session["sessionId"],
                "status": session["status"],
                "provider": session.get("provider"),
                "model": session.get("model"),
                "confidence": session.get("confidence"),
                "warnings": list(session.get("warnings") or []),
                "tokenUsage": dict(result.get("tokenUsage") or {}),
                "executionPlanVersion": session.get("executionPlanVersion"),
                "executionPackageVersion": session.get("executionPackageVersion"),
                "repositorySnapshotVersion": session.get("repositorySnapshotVersion"),
                **(payload or {}),
            },
        })

    def activity(self, session: dict, title: str, description: str, metadata: dict | None = None) -> None:
        if not self.platform:
            return
        self.platform.activity.add_activity({
            "activityType": "AIExecutionRuntime",
            "title": title,
            "description": description,
            "source": "ExecutionRuntime",
            "repositoryId": (session.get("runtimeContext") or {}).get("repositoryId"),
            "correlationId": session["correlationId"],
            "metadata": {"sessionId": session["sessionId"], **(metadata or {})},
        })
