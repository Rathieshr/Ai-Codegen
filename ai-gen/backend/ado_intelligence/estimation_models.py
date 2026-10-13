"""Persistent models for explainable estimation recommendations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .models import now_iso


class EstimationStatus(str, Enum):
    DRAFT = "Draft"
    ACCEPTED = "Accepted"
    EDITED = "Edited"
    REJECTED = "Rejected"
    STALE = "Stale"


@dataclass
class EstimationRecommendation:
    estimate_id: str
    work_item_id: str
    work_item_revision: int
    project_id: str
    team_id: str
    suggested_tasks: list[dict[str, Any]]
    story_points: int
    effort_range: dict[str, str]
    testing_effort: str
    review_effort: str
    uncertainty: dict[str, Any]
    confidence: float
    dependencies: list[dict[str, Any]]
    blockers: list[str]
    assumptions: list[str]
    similar_historical_items: list[dict[str, Any]]
    calibration: dict[str, Any]
    repository_impact: dict[str, Any]
    evidence: list[dict[str, Any]]
    status: EstimationStatus = EstimationStatus.DRAFT
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    accepted_by: str = ""
    rejected_by: str = ""
    edit_reason: str = ""
    parent_estimate_id: str = ""
    automation_recommendation_id: str = ""

    @classmethod
    def create(cls, **values: Any) -> "EstimationRecommendation":
        return cls(estimate_id=f"estimate-{uuid4().hex[:14]}", **values)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        for old, new in {
            "estimate_id": "estimateId", "work_item_id": "workItemId", "work_item_revision": "workItemRevision",
            "project_id": "projectId", "team_id": "teamId", "suggested_tasks": "suggestedTasks",
            "story_points": "storyPoints", "effort_range": "effortRange", "testing_effort": "testingEffort",
            "review_effort": "reviewEffort", "similar_historical_items": "similarHistoricalItems",
            "repository_impact": "repositoryImpact", "created_at": "createdAt", "updated_at": "updatedAt",
            "accepted_by": "acceptedBy", "rejected_by": "rejectedBy", "edit_reason": "editReason",
            "parent_estimate_id": "parentEstimateId", "automation_recommendation_id": "automationRecommendationId",
        }.items():
            value[new] = value.pop(old)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EstimationRecommendation":
        return cls(
            estimate_id=str(value.get("estimateId") or ""), work_item_id=str(value.get("workItemId") or ""),
            work_item_revision=int(value.get("workItemRevision") or 0), project_id=str(value.get("projectId") or ""),
            team_id=str(value.get("teamId") or ""), suggested_tasks=list(value.get("suggestedTasks") or []),
            story_points=int(value.get("storyPoints") or 0), effort_range=dict(value.get("effortRange") or {}),
            testing_effort=str(value.get("testingEffort") or ""), review_effort=str(value.get("reviewEffort") or ""),
            uncertainty=dict(value.get("uncertainty") or {}), confidence=float(value.get("confidence") or 0),
            dependencies=list(value.get("dependencies") or []), blockers=list(value.get("blockers") or []),
            assumptions=list(value.get("assumptions") or []), similar_historical_items=list(value.get("similarHistoricalItems") or []),
            calibration=dict(value.get("calibration") or {}), repository_impact=dict(value.get("repositoryImpact") or {}),
            evidence=list(value.get("evidence") or []), status=EstimationStatus(value.get("status") or "Draft"),
            created_at=str(value.get("createdAt") or now_iso()), updated_at=str(value.get("updatedAt") or now_iso()),
            accepted_by=str(value.get("acceptedBy") or ""), rejected_by=str(value.get("rejectedBy") or ""),
            edit_reason=str(value.get("editReason") or ""), parent_estimate_id=str(value.get("parentEstimateId") or ""),
            automation_recommendation_id=str(value.get("automationRecommendationId") or ""),
        )
