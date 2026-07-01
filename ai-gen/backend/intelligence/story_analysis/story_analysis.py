from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RepositoryEvidence:
    name: str
    type: str
    confidence: float
    reason: str
    source: str = "feature_dna"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "confidence": round(float(self.confidence), 2),
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True)
class Dependency:
    name: str
    reason: str
    confidence: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "reason": self.reason, "confidence": round(float(self.confidence), 2)}


@dataclass(frozen=True)
class PlanningBoundary:
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"inScope": list(self.in_scope), "outOfScope": list(self.out_of_scope)}


@dataclass(frozen=True)
class UserJourney:
    journey_id: str
    journey_name: str
    business_responsibility: str
    business_value: str
    persona: str
    dependencies: list[Dependency] = field(default_factory=list)
    repository_evidence: list[RepositoryEvidence] = field(default_factory=list)
    planning_boundary: PlanningBoundary = field(default_factory=PlanningBoundary)
    acceptance_themes: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "draft"
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "journeyId": self.journey_id,
            "journeyName": self.journey_name,
            "businessResponsibility": self.business_responsibility,
            "businessValue": self.business_value,
            "persona": self.persona,
            "dependencies": [item.to_dict() for item in self.dependencies],
            "repositoryEvidence": [item.to_dict() for item in self.repository_evidence],
            "planningBoundary": self.planning_boundary.to_dict(),
            "acceptanceThemes": list(self.acceptance_themes),
            "confidence": round(float(self.confidence), 2),
            "status": self.status,
            "order": int(self.order),
        }


@dataclass(frozen=True)
class StoryAnalysis:
    feature_id: int | str | None
    feature_dna: str
    business_responsibilities: list[str]
    user_journeys: list[UserJourney]
    system_responsibilities: list[str]
    acceptance_themes: list[str]
    planning_boundary: PlanningBoundary
    repository_evidence: list[RepositoryEvidence]
    dependencies: list[Dependency]
    implementation_areas: list[str]
    confidence: float
    diagnostics: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "featureId": self.feature_id,
            "featureDNA": self.feature_dna,
            "businessResponsibilities": list(self.business_responsibilities),
            "userJourneys": [journey.to_dict() for journey in self.user_journeys],
            "systemResponsibilities": list(self.system_responsibilities),
            "acceptanceThemes": list(self.acceptance_themes),
            "planningBoundary": self.planning_boundary.to_dict(),
            "repositoryEvidence": [item.to_dict() for item in self.repository_evidence],
            "dependencies": [item.to_dict() for item in self.dependencies],
            "implementationAreas": list(self.implementation_areas),
            "confidence": round(float(self.confidence), 2),
            "diagnostics": dict(self.diagnostics),
            "generatedAt": self.generated_at,
        }

