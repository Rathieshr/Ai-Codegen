from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ValidationStatus = Literal["Pending"]


@dataclass(frozen=True)
class PlanningEvidence:
    planning_context_version: str
    capabilities: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    applications: list[str] = field(default_factory=list)
    standards: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "planningContextVersion": self.planning_context_version,
            "capabilities": list(self.capabilities),
            "modules": list(self.modules),
            "flows": list(self.flows),
            "applications": list(self.applications),
            "standards": list(self.standards),
        }


@dataclass(frozen=True)
class PlanningArtifact:
    title: str
    description: str
    business_value: str
    acceptance_criteria: list[str] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    generated_using: PlanningEvidence = field(default_factory=lambda: PlanningEvidence("unknown"))
    confidence: float = 0.0
    validation_status: ValidationStatus = "Pending"
    artifact_type: str = "PlanningArtifact"
    duplicate_candidate: dict[str, Any] | None = None
    suggested_capability: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "businessValue": self.business_value,
            "acceptanceCriteria": list(self.acceptance_criteria),
            "personas": list(self.personas),
            "dependencies": list(self.dependencies),
            "risks": list(self.risks),
            "assumptions": list(self.assumptions),
            "generatedUsing": self.generated_using.to_dict(),
            "confidence": round(float(self.confidence), 2),
            "validationStatus": self.validation_status,
            "artifactType": self.artifact_type,
        }
        if self.duplicate_candidate:
            payload["duplicateCandidate"] = dict(self.duplicate_candidate)
        if self.suggested_capability:
            payload["suggestedCapability"] = self.suggested_capability
        return payload

