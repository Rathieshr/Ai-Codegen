"""Application service for Validation Trigger evaluation."""

from __future__ import annotations

from typing import Any

from ..events import RuntimeEventPublisher
from .decision_engine import ValidationTriggerEngine
from .decision_repository import ValidationTriggerRepository


class ValidationTriggerService:
    def __init__(
        self,
        repository: ValidationTriggerRepository,
        *,
        engine: ValidationTriggerEngine | None = None,
        governance: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.repository = repository
        self.engine = engine or ValidationTriggerEngine()
        self.governance = governance
        self.publisher = RuntimeEventPublisher(platform)

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("Validation Trigger request must be an object.")
        diff = request.get("engineeringDiff")
        result = request.get("executionResult")
        manifest = request.get("executionManifest")
        governance_result = self._governance(diff, result, manifest)
        try:
            decision = self.engine.decide(
                diff,
                result,
                manifest,
                manual_override=request.get("manualOverride"),
                policy=request.get("policy"),
                governance_result=governance_result,
            )
            saved = self.repository.save(decision)
            session = _event_session(saved, diff, result)
            self.publisher.publish(saved["eventType"], session, {
                "decisionId": saved["decisionId"],
                "engineeringDiffId": saved["engineeringDiffId"],
                "executionManifestId": saved["executionManifestId"],
                "validationRequired": saved["validationRequired"],
                "reason": saved["reason"],
                "confidence": saved["confidence"],
                "invoked": False,
            })
            self.publisher.activity(session, f"Validation {saved['decision'].casefold()}", saved["reason"], {"decisionId": saved["decisionId"]})
            return saved
        except Exception as exc:
            session = _event_session({"decision": "Blocked"}, diff, result)
            self.publisher.publish("ValidationBlocked", session, {"reason": str(exc), "invoked": False})
            raise

    def get(self, decision_id: str) -> dict[str, Any] | None:
        return self.repository.get(decision_id)

    def _governance(self, diff: Any, result: Any, manifest: Any) -> dict[str, Any]:
        if not self.governance or not isinstance(manifest, dict):
            return {}
        return self.governance.enforce_policies(manifest, {
            "operation": "Run Validation",
            "engineeringDiff": diff if isinstance(diff, dict) else {},
            "executionResult": result if isinstance(result, dict) else {},
        })


def _event_session(decision: dict[str, Any], diff: Any, result: Any) -> dict[str, Any]:
    diff = diff if isinstance(diff, dict) else {}
    result = result if isinstance(result, dict) else {}
    session_id = str(decision.get("sessionId") or result.get("sessionId") or diff.get("sessionId") or "validation_trigger")
    correlation_id = str(decision.get("correlationId") or result.get("correlationId") or (result.get("diagnostics") or {}).get("correlationId") or f"corr_{session_id}")
    repository_id = str((diff.get("repositorySnapshotAfter") or {}).get("repositoryId") or "")
    return {
        "sessionId": session_id,
        "status": str(decision.get("decision") or "Blocked"),
        "correlationId": correlation_id,
        "runtimeContext": {"repositoryId": repository_id},
    }
