from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CapabilityCandidate:
    name: str
    reason: str
    confidence: float
    repository_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reason": self.reason,
            "confidence": round(self.confidence, 2),
            "repositoryEvidence": list(self.repository_evidence),
            "repository_evidence": list(self.repository_evidence),
        }


@dataclass
class CapabilityRelationship:
    source: str
    relationship: str
    target: str
    reason: str
    confidence: float = 0.78

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relationship": self.relationship,
            "target": self.target,
            "reason": self.reason,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class CapabilityPriority:
    name: str
    priority: str
    reason: str
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "priority": self.priority,
            "reason": self.reason,
            "rank": self.rank,
        }


@dataclass
class PlanningBoundary:
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inScope": list(self.in_scope),
            "outOfScope": list(self.out_of_scope),
            "in_scope": list(self.in_scope),
            "out_of_scope": list(self.out_of_scope),
        }


@dataclass
class EpicAnalysis:
    epic_id: int | str | None
    business_problems: list[str]
    business_goals: list[str]
    desired_outcomes: list[str]
    required_capabilities: list[CapabilityCandidate]
    excluded_capabilities: list[CapabilityCandidate]
    capability_relationships: list[CapabilityRelationship]
    capability_priority: list[CapabilityPriority]
    planning_boundary: PlanningBoundary
    repository_evidence: list[dict[str, Any]]
    confidence: float
    diagnostics: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "epicId": self.epic_id,
            "epic_id": self.epic_id,
            "businessProblems": list(self.business_problems),
            "business_problems": list(self.business_problems),
            "businessGoals": list(self.business_goals),
            "business_goals": list(self.business_goals),
            "desiredOutcomes": list(self.desired_outcomes),
            "desired_outcomes": list(self.desired_outcomes),
            "requiredCapabilities": [item.to_dict() for item in self.required_capabilities],
            "required_capabilities": [item.to_dict() for item in self.required_capabilities],
            "excludedCapabilities": [item.to_dict() for item in self.excluded_capabilities],
            "excluded_capabilities": [item.to_dict() for item in self.excluded_capabilities],
            "capabilityRelationships": [item.to_dict() for item in self.capability_relationships],
            "capability_relationships": [item.to_dict() for item in self.capability_relationships],
            "capabilityPriority": [item.to_dict() for item in self.capability_priority],
            "capability_priority": [item.to_dict() for item in self.capability_priority],
            "planningBoundary": self.planning_boundary.to_dict(),
            "planning_boundary": self.planning_boundary.to_dict(),
            "repositoryEvidence": list(self.repository_evidence),
            "repository_evidence": list(self.repository_evidence),
            "confidence": round(self.confidence, 2),
            "diagnostics": dict(self.diagnostics),
            "generatedAt": self.generated_at,
            "generated_at": self.generated_at,
        }
