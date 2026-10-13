"""Application service for semantic Engineering Diff construction."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..comparison import EngineeringDiffEngine
from ..events import RuntimeEventPublisher
from .engineering_diff_repository import EngineeringDiffRepository


class EngineeringDiffService:
    def __init__(
        self,
        repository: EngineeringDiffRepository,
        *,
        engine: EngineeringDiffEngine | None = None,
        platform: Any | None = None,
    ) -> None:
        self.repository = repository
        self.engine = engine or EngineeringDiffEngine()
        self.publisher = RuntimeEventPublisher(platform)

    def build(self, request: dict[str, Any]) -> dict[str, Any]:
        event_session = _event_session(request)
        try:
            if not isinstance(request, dict):
                raise ValueError("Engineering Diff request must be an object.")
            before = request.get("repositorySnapshotBefore")
            after = request.get("repositorySnapshotAfter")
            execution_result = request.get("executionResult")
            value = self.engine.compare(before, after, execution_result)
            saved = self.repository.save(value)
            event_session = _event_session(request, saved)
            self.publisher.publish("EngineeringDiffCompleted", event_session, {
                "engineeringDiffId": saved["diffId"],
                "impact": saved["impact"]["level"],
                "changeCount": saved["summary"]["totalChanges"],
            })
            self.publisher.activity(
                event_session,
                "Engineering Diff completed",
                f"Detected {saved['summary']['totalChanges']} semantic engineering changes.",
                {"engineeringDiffId": saved["diffId"], "impact": saved["impact"]["level"]},
            )
            return saved
        except Exception as exc:
            self.publisher.publish("EngineeringDiffFailed", event_session, {"reason": str(exc)})
            self.publisher.activity(event_session, "Engineering Diff failed", str(exc))
            raise

    def get(self, diff_id: str) -> dict[str, Any] | None:
        return self.repository.get(diff_id)


def _event_session(request: Any, engineering_diff: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = request if isinstance(request, dict) else {}
    result = payload.get("executionResult") if isinstance(payload.get("executionResult"), dict) else {}
    before = payload.get("repositorySnapshotBefore") if isinstance(payload.get("repositorySnapshotBefore"), dict) else {}
    after = payload.get("repositorySnapshotAfter") if isinstance(payload.get("repositorySnapshotAfter"), dict) else {}
    session_id = str(result.get("sessionId") or (engineering_diff or {}).get("sessionId") or "engineering_diff")
    correlation_id = str(result.get("correlationId") or (result.get("diagnostics") or {}).get("correlationId") or f"corr_{session_id}")
    repository_id = str(after.get("repositoryId") or before.get("repositoryId") or "")
    return {
        "sessionId": session_id,
        "status": str((engineering_diff or {}).get("status") or "Failed"),
        "correlationId": correlation_id,
        "runtimeContext": {"repositoryId": repository_id},
        "engineeringDiff": deepcopy(engineering_diff),
    }
