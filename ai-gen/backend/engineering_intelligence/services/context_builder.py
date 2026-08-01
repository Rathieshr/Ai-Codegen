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
            "requirement_context": value.get("requirement_context") or value.get("requirement") or {},
            "repository_code_context": _bounded_code_context(
                value.get("repository_code_context") or repository
            ),
            "repository_markdown_context": _bounded_markdown_context(
                value.get("repository_markdown_context") or {}
            ),
            "project_intelligence_context": value.get("project_intelligence_context")
            or value.get("projectIntelligence") or {},
            "azure_devops_context": value.get("azure_devops_context") or azure_devops,
            "engineering_memory_context": value.get("engineering_memory_context") or memory,
            "knowledge_synthesis": value.get("knowledge_synthesis") or {},
            "azureDevOps": azure_devops,
            "impact": value.get("impact") or {},
            "reuse": value.get("reuse") or {},
            "readiness": value.get("readiness") or {},
            "sourceVersions": value.get("sourceVersions") or {},
            "correlationId": value.get("correlationId") or "",
        }

    buildOptimizedContext = build_optimized_context


def _bounded_code_context(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("graph", None)
    result["files"] = list(result.get("files") or [])[:20]
    return result


def _bounded_markdown_context(value: dict[str, Any]) -> dict[str, Any]:
    diagnostics = dict(value.get("diagnostics") or {})
    return {
        "selected": list(value.get("selected") or [])[:12],
        "conflicts": list(value.get("conflicts") or [])[:20],
        "diagnostics": diagnostics,
        "rejected": list(value.get("rejected") or [])[:40],
    }
