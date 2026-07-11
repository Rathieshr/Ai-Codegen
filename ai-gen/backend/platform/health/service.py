"""Health and diagnostics for platform foundation services."""

from __future__ import annotations

from typing import Any


class PlatformHealthService:
    def __init__(self, foundation: Any) -> None:
        self._foundation = foundation

    def status(self) -> dict[str, Any]:
        status = {
            "eventBusStatus": "healthy",
            "jobQueueStatus": "healthy",
            "agentRuntimeStatus": "healthy",
            "notificationStatus": "healthy",
            "activityLogStatus": "healthy",
            "auditStatus": "healthy",
        }
        orchestrator = getattr(self._foundation, "context_orchestrator", None)
        if orchestrator:
            status.update(orchestrator.health())
        else:
            status.update({
                "contextOrchestratorStatus": "not_registered",
                "rankingEngineStatus": "not_registered",
                "budgetManagerStatus": "not_registered",
                "contextSourceStatus": {},
            })
        return status
