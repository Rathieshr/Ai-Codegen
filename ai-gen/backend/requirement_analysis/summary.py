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
    document = analysis.get("analysisDocument") if isinstance(analysis.get("analysisDocument"), dict) else {}
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
        "summary": document.get("executiveSummary") or analysis.get("requirementSummary"),
        "planningRequirement": analysis.get("planningRequirement") or requirement.get("normalizedRequirement"),
        "businessGoals": [document["businessGoal"]] if document.get("businessGoal") else list(analysis.get("businessGoals") or []),
        "functionalRequirements": list(document.get("functionalRequirements") or analysis.get("functionalRequirements") or []),
        "nonFunctionalRequirements": list(document.get("candidateNonFunctionalRequirements") or analysis.get("nonFunctionalRequirements") or []),
        "acceptanceCriteria": list(document.get("acceptanceCriteria") or analysis.get("acceptanceCriteria") or []),
        "acceptanceCriteriaRecords": list(analysis.get("acceptanceCriteriaRecords") or []),
        "acceptanceCriteriaState": dict(analysis.get("acceptanceCriteriaState") or {}),
        "acceptanceCoverage": dict(analysis.get("acceptanceCoverage") or {}),
        "acceptanceEvidence": list(analysis.get("acceptanceEvidence") or []),
        "requirementFacts": dict(analysis.get("requirementFacts") or {}),
        "missingInformation": list(analysis.get("missingInformation") or []),
        "aiAssumptions": list(analysis.get("aiAssumptions") or []),
        "fieldOrigins": dict(analysis.get("fieldOrigins") or {}),
        "actors": [value for value in [document.get("primaryActor"), *(document.get("secondaryActors") or [])] if value] or list(analysis.get("actors") or []),
        "businessRules": list(document.get("businessRules") or analysis.get("businessRules") or []),
        "constraints": list(document.get("constraints") or analysis.get("constraints") or []),
        "dependencies": list(document.get("dependencies") or analysis.get("dependencies") or []),
        "risks": list(document.get("risks") or analysis.get("risks") or []),
        "openQuestions": list(document.get("openQuestions") or analysis.get("openQuestions") or []),
        "assumptions": list(document.get("assumptions") or analysis.get("assumptions") or []),
        "planningReadiness": dict(document.get("planningReadiness") or analysis.get("planningReadiness") or {}),
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
        "canonicalRequirementAnalysis": document,
        "correlationId": requirement.get("correlationId"),
    }
