"""Deterministic builder for the canonical Engineering Context."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .models import (
    ArchitectureSummary,
    AzureDevOpsSummary,
    DependencySummary,
    EngineeringContext,
    EngineeringMemorySummary,
    EngineeringSummary,
    ImpactSummary,
    RepositoryRecommendation,
    RepositorySummary,
    ReuseSummary,
    SimilaritySummary,
)


class EngineeringContextBuilder:
    """Assembles provider results without performing any intelligence queries."""

    def build(
        self,
        *,
        requirement: dict[str, Any],
        repository: RepositorySummary,
        azure_devops: AzureDevOpsSummary,
        memory: EngineeringMemorySummary,
        similarity: SimilaritySummary,
        architecture: ArchitectureSummary,
        dependencies: DependencySummary,
        repository_recommendation: RepositoryRecommendation,
        planning_recommendation: dict[str, Any],
        impact: ImpactSummary,
        reuse: ReuseSummary,
        readiness: dict[str, Any],
        project_intelligence: dict[str, Any] | None = None,
        relevant_documentation: list[dict[str, Any]] | None = None,
        correlation_id: str = "",
    ) -> EngineeringContext:
        versions = {
            "requirementContextVersion": requirement.get("contextVersion"),
            "analysisId": requirement.get("analysisId"),
            "repositorySnapshotVersion": repository.repositorySnapshotVersion,
            "workItemRevisions": {
                str(item.get("id") or item.get("workItemId")): int(item.get("revision") or item.get("rev") or 0)
                for item in azure_devops.existingPlanning
                if item.get("id") or item.get("workItemId")
            },
            "memoryVersions": [
                {"id": item.get("id"), "version": item.get("version"), "updatedAt": item.get("updatedAt")}
                for item in memory.matches
            ],
            "projectKnowledgeVersion": (
                (project_intelligence or {}).get("knowledge") or {}
            ).get("version"),
        }
        version = _digest(versions)
        context_id = "engineering-context-" + version
        summary = EngineeringSummary(
            repository=repository.repositoryName or "Continue without Repository",
            project=str(requirement.get("projectName") or requirement.get("projectId") or ""),
            planningMode=str(planning_recommendation.get("mode") or "AI_RECOMMENDED"),
            repositoryConfidence=repository.confidence,
            memoryCoverage=memory.coverage,
            similarityMatches=len(similarity.matches),
            engineeringComplexity=impact.engineeringComplexity,
            risk=impact.risk,
            readiness=str(readiness.get("status") or "ReadyWithRecommendations"),
        )
        return EngineeringContext(
            contextId=context_id,
            contextVersion=version,
            requirement=requirement,
            repository=repository,
            azureDevOps=azure_devops,
            engineeringMemory=memory,
            similarWork=similarity,
            architecture=architecture,
            dependencies=dependencies,
            repositoryRecommendation=repository_recommendation,
            planningRecommendationInput=planning_recommendation,
            impact=impact,
            reuse=reuse,
            readiness=readiness,
            summary=summary,
            projectIntelligence=dict(project_intelligence or {}),
            relevantDocumentation=list(relevant_documentation or []),
            correlationId=correlation_id,
            generatedAt=datetime.now(timezone.utc).isoformat(),
            sourceVersions=versions,
        )


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
