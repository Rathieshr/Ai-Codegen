"""Explainable Prompt Quality and confidence scoring."""

from __future__ import annotations

from typing import Any


def score_prompt(sections: list[dict[str, Any]], source_status: str) -> tuple[int, float, dict[str, int], dict[str, float]]:
    by_id = {str(section.get("id") or ""): section for section in sections}
    protected = {"repository_context", "implementation_guidance", "validation"}
    structure = round(20 * len(protected.intersection(by_id)) / len(protected))
    clarity = 20

    repository = _content(by_id.get("repository_context"))
    repository_mode = str(repository.get("repositoryMode") or "Unavailable")
    evidence = bool(repository.get("evidenceAvailable"))
    grounding = 20 if repository_mode == "CodeIndexed" and evidence else 12 if repository_mode == "KnowledgeSnapshot" else 4

    validation = _content(by_id.get("validation"))
    acceptance = validation.get("acceptanceCriteria") if isinstance(validation, dict) else []
    acceptance_score = 20 if isinstance(acceptance, list) and acceptance else 8

    implementation = _content(by_id.get("implementation_guidance"))
    instructions = _content(by_id.get("instructions"))
    constraints = _content(by_id.get("constraints"))
    actionability = (10 if implementation else 0) + (5 if instructions else 0) + (5 if constraints else 0)
    quality_breakdown = {
        "structure": structure,
        "clarity": clarity,
        "repositoryGrounding": grounding,
        "acceptanceCoverage": acceptance_score,
        "actionability": actionability,
    }
    quality = sum(quality_breakdown.values())

    confidence_breakdown = {
        "sourceReady": 0.20 if source_status == "Ready" else 0.0,
        "repositoryEvidence": 0.25 if grounding == 20 else 0.15 if grounding == 12 else 0.05,
        "acceptanceEvidence": 0.20 if acceptance_score == 20 else 0.08,
        "implementationEvidence": 0.15 if implementation else 0.0,
        "promptQuality": round(0.20 * quality / 100, 4),
    }
    confidence = round(min(1.0, sum(confidence_breakdown.values())), 2)
    return quality, confidence, quality_breakdown, confidence_breakdown


def _content(section: dict[str, Any] | None) -> Any:
    return section.get("content") if isinstance(section, dict) else None
