"""Application service for Pull Request candidate generation."""

from __future__ import annotations

from typing import Any

from ..events import RuntimeEventPublisher
from .candidate_engine import PRCandidateGenerator
from .candidate_repository import PRCandidateRepository


class PRCandidateService:
    def __init__(self, repository: PRCandidateRepository, *, generator: PRCandidateGenerator | None = None, platform: Any | None = None) -> None:
        self.repository = repository
        self.generator = generator or PRCandidateGenerator()
        self.publisher = RuntimeEventPublisher(platform)

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("Pull Request candidate request must be an object.")
        candidate = self.generator.generate(
            request.get("engineeringDiff"),
            request.get("validationResult") or request.get("validation"),
            request.get("qaResult") or request.get("qa"),
            request.get("executionManifest"),
        )
        saved = self.repository.save(candidate)
        session = _event_session(saved)
        self.publisher.publish("PRCandidateCreated", session, {
            "candidateId": saved["candidateId"],
            "candidateType": saved["candidateType"],
            "confidence": saved["confidence"],
            "created": False,
            "pullRequestId": "",
            "gitOperations": 0,
            "azureDevOpsWrites": 0,
        })
        self.publisher.activity(session, "Pull Request candidate generated", "A reviewable PR summary was generated without creating a Git pull request.", {"candidateId": saved["candidateId"]})
        return saved

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        return self.repository.get(candidate_id)

    def list(self) -> dict[str, Any]:
        candidates = self.repository.list()
        return {"candidates": candidates, "count": len(candidates)}


def _event_session(candidate: dict[str, Any]) -> dict[str, Any]:
    lineage = candidate.get("sourceLineage") or {}
    session_id = str(lineage.get("sessionId") or "pr_candidate")
    correlation_id = str(lineage.get("correlationId") or f"corr_{session_id}")
    return {"sessionId": session_id, "status": candidate["status"], "correlationId": correlation_id, "runtimeContext": {}}
