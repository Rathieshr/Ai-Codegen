"""Application service for Engineering Memory candidate review."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..events import RuntimeEventPublisher
from .candidate_engine import MemoryCandidateGenerator
from .candidate_repository import MemoryCandidateRepository


class MemoryCandidateService:
    def __init__(self, repository: MemoryCandidateRepository, *, generator: MemoryCandidateGenerator | None = None, platform: Any | None = None) -> None:
        self.repository = repository
        self.generator = generator or MemoryCandidateGenerator()
        self.publisher = RuntimeEventPublisher(platform)

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("Memory Candidate request must be an object.")
        project_id = str(request.get("projectId") or "")
        report = self.generator.generate(
            request.get("executionResult"),
            request.get("validationResult"),
            request.get("qaResult"),
            request.get("engineeringDiff"),
            existing_memories=request.get("existingMemory") or request.get("existingMemories") or [],
            existing_candidates=self.repository.list(project_id),
            policy=request.get("policy"),
            project_id=project_id,
            organization_id=str(request.get("organizationId") or ""),
        )
        report["candidates"] = self.repository.save_many(report["candidates"])
        for candidate in report["candidates"]:
            self._publish(candidate)
        return report

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        return self.repository.get(candidate_id)

    def list(self, project_id: str = "") -> dict[str, Any]:
        candidates = self.repository.list(project_id)
        return {"candidates": candidates, "count": len(candidates)}

    def approve(self, candidate_id: str, actor: str = "") -> dict[str, Any]:
        candidate = self._pending(candidate_id)
        candidate["status"] = "Approved"
        candidate["approvalStatus"] = "Approved"
        candidate["approvedBy"] = actor or "HEI Reviewer"
        candidate["approvedAt"] = _now()
        candidate["updatedAt"] = candidate["approvedAt"]
        candidate["stored"] = False
        candidate["indexed"] = False
        saved = self.repository.update(candidate)
        self._activity(saved, "Engineering Memory candidate approved", "Candidate approved for a separate Engineering Memory capture step.")
        return saved

    def reject(self, candidate_id: str, actor: str = "", reason: str = "") -> dict[str, Any]:
        candidate = self._pending(candidate_id)
        candidate["status"] = "Rejected"
        candidate["approvalStatus"] = "Rejected"
        candidate["rejectedBy"] = actor or "HEI Reviewer"
        candidate["rejectedAt"] = _now()
        candidate["updatedAt"] = candidate["rejectedAt"]
        candidate["rejectionReasons"] = list(dict.fromkeys([*(candidate.get("rejectionReasons") or []), reason or "Rejected during human review."]))
        candidate["eventType"] = "MemoryCandidateRejected"
        saved = self.repository.update(candidate)
        self._publish(saved)
        return saved

    def _pending(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.repository.get(candidate_id)
        if not candidate:
            raise ValueError("Engineering Memory candidate not found.")
        if candidate.get("approvalStatus") != "Pending":
            raise ValueError(f"Engineering Memory candidate is already {candidate.get('approvalStatus') or candidate.get('status')}.")
        return candidate

    def _publish(self, candidate: dict[str, Any]) -> None:
        session = _event_session(candidate)
        self.publisher.publish(candidate["eventType"], session, {
            "candidateId": candidate["candidateId"],
            "candidateType": candidate["candidateType"],
            "approvalRequired": True,
            "approvalStatus": candidate["approvalStatus"],
            "stored": False,
            "indexed": False,
            "reason": "; ".join(candidate.get("rejectionReasons") or []) or "Candidate is ready for human review.",
        })
        self._activity(candidate, candidate["eventType"], "Candidate was generated without writing Engineering Memory.")

    def _activity(self, candidate: dict[str, Any], title: str, description: str) -> None:
        self.publisher.activity(_event_session(candidate), title, description, {"candidateId": candidate["candidateId"]})


def _event_session(candidate: dict[str, Any]) -> dict[str, Any]:
    lineage = candidate.get("sourceLineage") or {}
    session_id = str(lineage.get("sessionId") or "memory_candidate")
    correlation_id = str(lineage.get("correlationId") or f"corr_{session_id}")
    return {"sessionId": session_id, "status": candidate.get("status") or "PendingApproval", "correlationId": correlation_id, "runtimeContext": {}}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
