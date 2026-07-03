"""History helpers for agent workflows."""

from __future__ import annotations

from typing import Any


class AgentHistory:
    def build(self, workflows: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for event in events:
            history.append(
                {
                    "time": event.get("createdAt"),
                    "type": "Event",
                    "agent": event.get("source") or "Event Bus",
                    "message": event.get("eventType"),
                    "artifactType": event.get("artifactType"),
                    "artifactId": event.get("artifactId"),
                    "status": "Recorded",
                }
            )
        for workflow in workflows:
            for item in workflow.get("timeline", []):
                history.append(
                    {
                        "time": item.get("time"),
                        "type": "Workflow",
                        "agent": workflow.get("agent"),
                        "message": item.get("message"),
                        "artifactType": workflow.get("artifactType"),
                        "artifactId": workflow.get("artifactId"),
                        "status": item.get("status"),
                    }
                )
        return sorted(history, key=lambda item: str(item.get("time") or ""))[-100:]
