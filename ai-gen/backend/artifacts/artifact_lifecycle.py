"""Shared lifecycle constants and transition helpers for HEI artifacts."""

from __future__ import annotations

from dataclasses import dataclass


class ArtifactStatus:
    DRAFT = "Draft"
    ANALYSIS = "Analysis"
    REVIEW = "Review"
    APPROVAL = "Approval"
    GENERATION = "Generation"
    VALIDATION = "Validation"
    DNA = "DNA"
    VERSIONED = "Versioned"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    PUBLISHED = "Published"


LIFECYCLE_ORDER = [
    ArtifactStatus.DRAFT,
    ArtifactStatus.ANALYSIS,
    ArtifactStatus.REVIEW,
    ArtifactStatus.APPROVAL,
    ArtifactStatus.GENERATION,
    ArtifactStatus.VALIDATION,
    ArtifactStatus.DNA,
    ArtifactStatus.VERSIONED,
]


TERMINAL_STATUSES = {ArtifactStatus.REJECTED, ArtifactStatus.PUBLISHED}


@dataclass(frozen=True)
class LifecycleResult:
    artifact_id: str
    previous_status: str
    status: str
    event: str
    allowed: bool
    reason: str = ""

