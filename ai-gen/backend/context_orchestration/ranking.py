"""Configurable, deterministic candidate ranking."""

from __future__ import annotations

from typing import Protocol

from .models import ContextCandidate, ContextRequest, ContextSourceType


DEFAULT_WEIGHTS = {
    "intent": 0.30, "repositoryEvidence": 0.20, "artifactLineage": 0.15,
    "purposeSuitability": 0.15, "knowledgeMemoryMatch": 0.10, "freshness": 0.10,
}


class IContextRankingEngine(Protocol):
    version: str
    def rank(self, request: ContextRequest, candidates: list[ContextCandidate]) -> list[ContextCandidate]: ...


class ContextRankingEngine:
    version = "deterministic-v1"

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    def rank(self, request: ContextRequest, candidates: list[ContextCandidate]) -> list[ContextCandidate]:
        for candidate in candidates:
            artifact_lineage = float(candidate.metadata.get("artifactLineageScore", candidate.relevance_score))
            purpose = float(candidate.metadata.get("purposeSuitabilityScore", candidate.relevance_score))
            match = float(candidate.metadata.get("knowledgeMemoryScore", candidate.relevance_score))
            candidate.final_score = round(
                self.weights["intent"] * candidate.relevance_score
                + self.weights["repositoryEvidence"] * candidate.evidence_score
                + self.weights["artifactLineage"] * artifact_lineage
                + self.weights["purposeSuitability"] * purpose
                + self.weights["knowledgeMemoryMatch"] * match
                + self.weights["freshness"] * candidate.freshness_score,
                4,
            )
            if candidate.source_type == ContextSourceType.REPOSITORY and candidate.metadata.get("directEvidence"):
                candidate.reasons.append("direct_repository_evidence")
        return sorted(candidates, key=lambda item: (-item.final_score, item.candidate_id))
