from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

WorkItemType = Literal["Epic", "Feature", "Story", "Task"]
PlanningSource = Literal["intent", "repository", "knowledge_registry", "capability_engine", "parent"]
GenerationRole = Literal["ProductOwner", "ProductManager", "ScrumMaster", "SeniorDeveloper", "TechLead"]


@dataclass(frozen=True)
class PlanningLineage:
    derived_from_id: int | str | None
    derived_from_type: str
    derived_from_title: str
    derivation_rule: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "derivedFromId": self.derived_from_id,
            "derivedFromType": self.derived_from_type,
            "derivedFromTitle": self.derived_from_title,
            "derivationRule": self.derivation_rule,
        }


@dataclass(frozen=True)
class PlanningReference:
    name: str
    type: str
    confidence: float
    source: PlanningSource
    reason: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "type": self.type,
            "confidence": round(float(self.confidence), 2),
            "source": self.source,
            "reason": self.reason,
        }
        if self.evidence:
            payload["evidence"] = list(self.evidence)
        return payload


@dataclass(frozen=True)
class RejectedPlanningContext:
    name: str
    type: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "reason": self.reason}


@dataclass(frozen=True)
class ExistingArtifactSummary:
    id: int | str | None
    type: str
    title: str
    purpose: str = ""
    duplicate_risk: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "purpose": self.purpose,
            "duplicateRisk": self.duplicate_risk,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PlanningContext:
    work_item_id: int | str | None
    work_item_type: str
    lineage: PlanningLineage
    business_goal: str
    user_problem: str
    expected_outcome: str
    selected_capabilities: list[PlanningReference] = field(default_factory=list)
    selected_modules: list[PlanningReference] = field(default_factory=list)
    selected_flows: list[PlanningReference] = field(default_factory=list)
    selected_applications: list[PlanningReference] = field(default_factory=list)
    selected_dependencies: list[PlanningReference] = field(default_factory=list)
    selected_standards: list[PlanningReference] = field(default_factory=list)
    rejected_context: list[RejectedPlanningContext] = field(default_factory=list)
    generation_role: str = "ProductOwner"
    generation_objective: str = "Prepare controlled planning context."
    constraints: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    existing_children: list[ExistingArtifactSummary] = field(default_factory=list)
    confidence: float = 0.0
    token_estimate: int = 0
    parent_id: int | str | None = None
    parent_type: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "workItemId": self.work_item_id,
            "workItemType": self.work_item_type,
            "lineage": self.lineage.to_dict(),
            "businessGoal": self.business_goal,
            "userProblem": self.user_problem,
            "expectedOutcome": self.expected_outcome,
            "selectedCapabilities": [item.to_dict() for item in self.selected_capabilities],
            "selectedModules": [item.to_dict() for item in self.selected_modules],
            "selectedFlows": [item.to_dict() for item in self.selected_flows],
            "selectedApplications": [item.to_dict() for item in self.selected_applications],
            "selectedDependencies": [item.to_dict() for item in self.selected_dependencies],
            "selectedStandards": [item.to_dict() for item in self.selected_standards],
            "rejectedContext": [item.to_dict() for item in self.rejected_context],
            "generationRole": self.generation_role,
            "generationObjective": self.generation_objective,
            "constraints": list(self.constraints),
            "risks": list(self.risks),
            "existingChildren": [item.to_dict() for item in self.existing_children],
            "confidence": round(float(self.confidence), 2),
            "tokenEstimate": int(self.token_estimate),
            "generatedAt": self.generated_at,
            "diagnostics": dict(self.diagnostics),
        }
        if self.parent_id is not None:
            payload["parentId"] = self.parent_id
        if self.parent_type:
            payload["parentType"] = self.parent_type
        return payload
