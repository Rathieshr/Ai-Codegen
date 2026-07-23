"""Canonical Requirement Summary projection used by downstream intelligence."""

from __future__ import annotations

from typing import Any


def build_requirement_summary(requirement: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Build the immutable planning boundary from reviewed requirement intelligence."""
    metadata = requirement.get("metadata") if isinstance(requirement.get("metadata"), dict) else {}
    attributes = metadata.get("attributes") if isinstance(metadata.get("attributes"), dict) else {}
    suggestion = analysis.get("repositorySuggestion") if isinstance(analysis.get("repositorySuggestion"), dict) else {}
    selected = suggestion.get("suggestedRepository") if isinstance(suggestion.get("suggestedRepository"), dict) else {}
    review_context = analysis.get("reviewContext") if isinstance(analysis.get("reviewContext"), dict) else {}
    return {
        "summaryType": "RequirementSummary",
        "requirementId": requirement.get("requirementId"),
        "contextVersion": requirement.get("contextVersion"),
        "contentHash": requirement.get("contentHash"),
        "analysisId": analysis.get("analysisId"),
        "analysisStatus": analysis.get("reviewStatus"),
        "sourceType": requirement.get("sourceType"),
        "sourceReference": metadata.get("sourceReference"),
        "title": requirement.get("title"),
        "summary": analysis.get("requirementSummary"),
        "planningRequirement": analysis.get("planningRequirement") or requirement.get("normalizedRequirement"),
        "businessGoals": list(analysis.get("businessGoals") or []),
        "functionalRequirements": list(analysis.get("functionalRequirements") or []),
        "nonFunctionalRequirements": list(analysis.get("nonFunctionalRequirements") or []),
        "acceptanceCriteria": list(analysis.get("acceptanceCriteria") or []),
        "acceptanceCriteriaState": dict(analysis.get("acceptanceCriteriaState") or {}),
        "fieldOrigins": dict(analysis.get("fieldOrigins") or {}),
        "actors": list(analysis.get("actors") or []),
        "businessRules": list(analysis.get("businessRules") or []),
        "constraints": list(analysis.get("constraints") or []),
        "dependencies": list(analysis.get("dependencies") or []),
        "risks": list(analysis.get("risks") or []),
        "openQuestions": list(analysis.get("openQuestions") or []),
        "assumptions": list(analysis.get("assumptions") or []),
        "planningReadiness": dict(analysis.get("planningReadiness") or {}),
        "qualityScore": analysis.get("requirementQualityScore"),
        "confidence": analysis.get("confidence"),
        "projectId": metadata.get("projectId"),
        "projectName": metadata.get("projectName"),
        "repository": {
            "repositoryId": metadata.get("repositoryId"),
            "name": attributes.get("repositoryName") or selected.get("name"),
            "branch": metadata.get("branch"),
            "confidence": suggestion.get("confidence", 0),
            "reason": suggestion.get("reason", ""),
            "source": suggestion.get("source", ""),
        },
        "engineeringMemory": dict(review_context.get("engineeringMemory") or {}),
        "correlationId": requirement.get("correlationId"),
    }
