"""Application service for deterministic QA Trigger planning."""

from __future__ import annotations

from typing import Any

from ..events import RuntimeEventPublisher
from .plan_engine import QATriggerEngine
from .plan_repository import QAExecutionPlanRepository


class QATriggerService:
    def __init__(self, repository: QAExecutionPlanRepository, *, engine: QATriggerEngine | None = None, platform: Any | None = None) -> None:
        self.repository = repository
        self.engine = engine or QATriggerEngine()
        self.publisher = RuntimeEventPublisher(platform)

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("QA Trigger request must be an object.")
        diff = request.get("engineeringDiff")
        validation = request.get("validationResult")
        manifest = request.get("executionManifest")
        plan = self.engine.plan(diff, validation, manifest)
        saved = self.repository.save(plan)
        session = _event_session(saved, diff, validation)
        self.publisher.publish(saved["eventType"], session, {
            "qaExecutionPlanId": saved["planId"],
            "engineeringDiffId": saved["engineeringDiffId"],
            "validationResultId": saved["validationResultId"],
            "executionManifestId": saved["executionManifestId"],
            "qaRequired": saved["qaRequired"],
            "activities": [item["type"] for item in saved["requiredActivities"]],
            "reason": saved["reason"],
            "invoked": False,
        })
        self.publisher.activity(session, f"QA {saved['decision'].casefold()}", saved["reason"], {"qaExecutionPlanId": saved["planId"]})
        return saved

    def get(self, plan_id: str) -> dict[str, Any] | None:
        return self.repository.get(plan_id)


def _event_session(plan: dict[str, Any], diff: Any, validation: Any) -> dict[str, Any]:
    diff = diff if isinstance(diff, dict) else {}
    validation = validation if isinstance(validation, dict) else {}
    session_id = str(plan.get("sessionId") or diff.get("sessionId") or validation.get("sessionId") or "qa_trigger")
    correlation_id = str(plan.get("correlationId") or validation.get("correlationId") or (validation.get("diagnostics") or {}).get("correlationId") or f"corr_{session_id}")
    repository_id = str((diff.get("repositorySnapshotAfter") or {}).get("repositoryId") or "")
    return {"sessionId": session_id, "status": plan["decision"], "correlationId": correlation_id, "runtimeContext": {"repositoryId": repository_id}}
