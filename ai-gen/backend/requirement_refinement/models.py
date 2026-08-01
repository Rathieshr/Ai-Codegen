"""Canonical models for AI Requirement Refinement."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequirementRefinement:
    refinement_id: str
    requirement_id: str
    original_requirement: str
    refined_requirement: str
    executive_summary: str
    requirement_summary: str
    business_goal: str
    business_objective: str
    problem_statement: str
    user_intent: str
    primary_actor: str
    secondary_actors: list[str]
    core_capability: str
    core_capabilities: list[str]
    expected_outcome: str
    business_entities: list[str]
    engineering_concepts: list[str]
    domain_terminology: list[str]
    repository_search_hints: list[str]
    markdown_search_hints: list[str]
    azure_devops_search_hints: list[str]
    possible_module_names: list[str]
    possible_feature_names: list[str]
    potential_domain_terms: list[str]
    potential_search_keywords: list[str]
    potential_repository_terms: list[str]
    potential_azure_devops_terms: list[str]
    potential_markdown_terms: list[str]
    requirement_intent: dict[str, Any]
    changes: list[dict[str, str]] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    clarification_candidates: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "PendingReview"
    provider: str = "Deterministic"
    model: str = ""
    prompt_version: str = ""
    version: int = 1
    generated_at: str = ""
    accepted_by: str = ""
    accepted_at: str = ""
    revision_history: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {
            key.split("_")[0] + "".join(part.capitalize() for part in key.split("_")[1:]): item
            for key, item in value.items()
        }
