"""Bounded consumer projections from the canonical Engineering Context."""

from __future__ import annotations

from typing import Any

from ..models import EngineeringContext


class ContextBuilder:
    """Removes broad graph and source collections from workflow prompt input."""

    def build_optimized_context(
        self, context: EngineeringContext | dict[str, Any],
    ) -> dict[str, Any]:
        value = context.to_dict() if isinstance(context, EngineeringContext) else dict(context)
        repository = dict(value.get("repository") or {})
        repository.pop("graph", None)
        repository["files"] = list(repository.get("files") or [])[:20]
        azure_devops = dict(value.get("azureDevOps") or {})
        azure_devops["existingPlanning"] = list(azure_devops.get("existingPlanning") or [])[:30]
        memory = dict(value.get("engineeringMemory") or {})
        memory["matches"] = list(memory.get("matches") or [])[:20]
        return {
            "contextId": value.get("contextId"),
            "contextVersion": value.get("contextVersion"),
            "requirement": value.get("requirement") or {},
            "repository": repository,
            "relevantDocumentation": value.get("relevantDocumentation") or [],
            "architecture": value.get("architecture") or {},
            "dependencies": value.get("dependencies") or {},
            "similarWork": value.get("similarWork") or {},
            "engineeringMemory": memory,
            "projectIntelligence": value.get("projectIntelligence") or {},
            "azureDevOps": azure_devops,
            "impact": value.get("impact") or {},
            "reuse": value.get("reuse") or {},
            "readiness": value.get("readiness") or {},
            "sourceVersions": value.get("sourceVersions") or {},
            "correlationId": value.get("correlationId") or "",
        }

    buildOptimizedContext = build_optimized_context
