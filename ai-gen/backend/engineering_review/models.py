"""Canonical Engineering Review contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


REVIEW_SECTIONS = (
    "Business Review",
    "Architecture Review",
    "Repository Review",
    "Acceptance Criteria Review",
    "Dependency Review",
    "Estimate Review",
    "Risk Review",
    "Testing Review",
    "Deployment Review",
)

INLINE_TARGETS = (
    "Epic",
    "Feature",
    "Story",
    "Task",
    "Acceptance Criterion",
    "Engineering Note",
    "Estimate",
    "Dependency",
    "Repository Mapping",
)

CHANGE_REQUEST_TYPES = (
    "Story Split",
    "Story Merge",
    "Estimate Change",
    "Repository Change",
    "Acceptance Criteria Update",
    "Dependency Update",
    "Architecture Review",
    "Business Clarification",
)


@dataclass(frozen=True)
class ReviewStageDefinition:
    stageId: str
    name: str
    role: str
    order: int
    required: bool = True
    assignedReviewer: str = ""


@dataclass
class EngineeringReview:
    reviewId: str
    proposalId: str
    proposalVersion: int
    contextVersion: str
    knowledgeVersion: str
    recommendationVersion: int
    status: str
    owner: str
    currentStageId: str
    stages: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    comments: list[dict[str, Any]] = field(default_factory=list)
    changeRequests: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    readiness: dict[str, Any] = field(default_factory=dict)
    affectedRepositories: list[str] = field(default_factory=list)
    affectedTeams: list[str] = field(default_factory=list)
    expiresAt: str = ""
    createdAt: str = ""
    updatedAt: str = ""
    approvedAt: str = ""
    approvedBy: str = ""

