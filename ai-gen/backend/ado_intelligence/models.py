"""Domain models for read-only Azure DevOps work-item intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RecommendationStatus(str, Enum):
    DRAFT = "Draft"
    NEEDS_REVIEW = "NeedsReview"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    APPLIED = "Applied"
    STALE = "Stale"


@dataclass
class WorkItemRecommendation:
    recommendation_id: str
    work_item_id: str
    work_item_revision: int
    recommendation_type: str
    current_value: Any
    proposed_value: Any
    reasons: list[str]
    evidence: list[dict[str, Any]]
    confidence: float
    status: RecommendationStatus = RecommendationStatus.DRAFT
    created_at: str = field(default_factory=now_iso)
    approved_by: str = ""
    approved_at: str = ""
    rejected_by: str = ""
    rejected_at: str = ""
    analysis_id: str = ""
    project_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        mapping = {"recommendation_id": "recommendationId", "work_item_id": "workItemId", "work_item_revision": "workItemRevision", "recommendation_type": "recommendationType", "current_value": "currentValue", "proposed_value": "proposedValue", "created_at": "createdAt", "approved_by": "approvedBy", "approved_at": "approvedAt", "rejected_by": "rejectedBy", "rejected_at": "rejectedAt", "analysis_id": "analysisId", "project_id": "projectId"}
        for old, new in mapping.items():
            value[new] = value.pop(old)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorkItemRecommendation":
        return cls(
            recommendation_id=str(value.get("recommendationId") or ""), work_item_id=str(value.get("workItemId") or ""),
            work_item_revision=int(value.get("workItemRevision") or 0), recommendation_type=str(value.get("recommendationType") or ""),
            current_value=value.get("currentValue"), proposed_value=value.get("proposedValue"), reasons=list(value.get("reasons") or []),
            evidence=list(value.get("evidence") or []), confidence=float(value.get("confidence") or 0),
            status=RecommendationStatus(value.get("status") or "Draft"), created_at=str(value.get("createdAt") or now_iso()),
            approved_by=str(value.get("approvedBy") or ""), approved_at=str(value.get("approvedAt") or ""),
            rejected_by=str(value.get("rejectedBy") or ""), rejected_at=str(value.get("rejectedAt") or ""),
            analysis_id=str(value.get("analysisId") or ""), project_id=str(value.get("projectId") or ""),
        )
