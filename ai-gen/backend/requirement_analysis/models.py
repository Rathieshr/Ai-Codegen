"""Canonical Requirement Analysis models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequirementFinding:
    text: str
    reason: str
    evidence: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "reason": self.reason,
            "evidence": self.evidence or self.text,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class RequirementAnalysis:
    analysis_id: str
    requirement_id: str
    context_version: str
    content_hash: str
    requirement_summary: str
    planning_requirement: str
    planning_readiness: dict[str, Any]
    requirement_quality_score: int
    confidence: float
    business_goals: list[str] = field(default_factory=list)
    functional_requirements: list[str] = field(default_factory=list)
    non_functional_requirements: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing_acceptance_criteria: list[RequirementFinding] = field(default_factory=list)
    ambiguous_requirements: list[RequirementFinding] = field(default_factory=list)
    conflicting_requirements: list[RequirementFinding] = field(default_factory=list)
    duplicate_requirements: list[RequirementFinding] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    review_context: dict[str, Any] = field(default_factory=dict)
    review_status: str = "Pending"
    approved_by: str = ""
    approved_at: str = ""
    approved_content_hash: str = ""
    approved_context_version: str = ""
    analyzed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        result = {
            "analysisId": value.pop("analysis_id"),
            "requirementId": value.pop("requirement_id"),
            "contextVersion": value.pop("context_version"),
            "contentHash": value.pop("content_hash"),
            "requirementSummary": value.pop("requirement_summary"),
            "planningRequirement": value.pop("planning_requirement"),
            "planningReadiness": value.pop("planning_readiness"),
            "requirementQualityScore": value.pop("requirement_quality_score"),
            "confidence": value.pop("confidence"),
            "analyzedAt": value.pop("analyzed_at"),
            "reviewContext": value.pop("review_context"),
            "reviewStatus": value.pop("review_status"),
            "approvedBy": value.pop("approved_by"),
            "approvedAt": value.pop("approved_at"),
            "approvedContentHash": value.pop("approved_content_hash"),
            "approvedContextVersion": value.pop("approved_context_version"),
        }
        for key, item in value.items():
            camel = key.split("_")[0] + "".join(part.capitalize() for part in key.split("_")[1:])
            result[camel] = item
        return result
