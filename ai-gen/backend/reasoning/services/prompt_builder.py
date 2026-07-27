"""Provider-aware prompt construction from EngineeringContext only."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.prompt_budget import PromptSection, budgetProfileForProvider, buildPrompt, estimateTokens

from ..models import BuiltReasoningPrompt, ReasoningRequest
from .prompt_templates import PROMPT_VERSION, resolve_template


class PromptBuilder:
    def build(
        self,
        request: ReasoningRequest,
        *,
        provider: str,
        model: str = "",
    ) -> BuiltReasoningPrompt:
        context = _validate_context(request.engineeringContext)
        template = resolve_template(request.workflowType)
        catalog = _evidence_catalog(context)
        sections = [
            _section("role", "Role", template.role, True, 100, False, "template"),
            _section("objective", "Objective", template.objective, True, 100, False, "template"),
            _section(
                "current_work_item", "Current Work Item",
                request.userRequirement or _requirement_text(context), True, 100, True, "engineering_context",
            ),
            *(
                [
                    _section(
                        "current_artifact",
                        "Current Planning Artifact",
                        request.options["proposalSummary"],
                        True,
                        95,
                        True,
                        "planning_proposal",
                    )
                ]
                if request.options.get("proposalSummary")
                else []
            ),
            _section("current_intent", "Engineering Intent", _intent(context), True, 100, True, "engineering_context"),
            _section("repository_evidence", "Repository Evidence", _repository(context), False, 80, True, "repository"),
            _section("knowledge_summary", "Knowledge and Memory", _knowledge(context), False, 60, True, "knowledge"),
            _section("planning_boundary", "Boundaries and Constraints", _boundaries(context), True, 90, True, "engineering_context"),
            _section("validation", "Risk and Validation Context", _validation(context), False, 85, True, "engineering_context"),
            _section("evidence_catalog", "Evidence Catalog", catalog, True, 95, True, "engineering_context"),
            _section("instructions", "Instructions", list(template.instructions), True, 100, False, "template"),
            _section(
                "output_schema", "Output Schema",
                _output_schema(request.workflowType), True, 100, False, "schema",
            ),
        ]
        profile = budgetProfileForProvider(
            provider or "deterministic", model, operation=f"reason_{_key(request.workflowType)}",
        )
        built = buildPrompt(sections, profile)
        version = _prompt_version(request, provider, model)
        return BuiltReasoningPrompt(
            prompt=str(built["prompt"]),
            promptVersion=version,
            sections=[item.to_dict() for item in built["sections"]],
            evidenceCatalog=catalog,
            diagnostics=dict(built["diagnostics"]),
        )


def _validate_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Reasoning AI requires EngineeringContext as a dictionary.")
    forbidden = {
        "rawRepository", "repositoryDump", "rawMarkdown", "sourceCode",
        "knowledge_registry", "projectProfile", "repositorySnapshot",
    }
    present = sorted(forbidden & set(value))
    if present:
        raise ValueError(
            "Reasoning AI accepts EngineeringContext only; remove raw sources: "
            + ", ".join(present)
        )
    if not value.get("contextId") and not value.get("contextVersion"):
        raise ValueError("EngineeringContext must include contextId or contextVersion.")
    return value


def _section(
    identifier: str, name: str, content: Any, required: bool,
    priority: int, compressible: bool, source: str,
) -> PromptSection:
    serialized = json.dumps(content, ensure_ascii=True, separators=(",", ":")) if not isinstance(content, str) else content
    return PromptSection(
        id=identifier,
        name=name,
        priority=priority,
        estimatedTokens=estimateTokens(serialized),
        required=required,
        compressible=compressible,
        source=source,
        content=content,
    )


def _requirement_text(context: dict[str, Any]) -> str:
    requirement = context.get("requirement") or {}
    return str(
        requirement.get("planningRequirement")
        or requirement.get("normalizedRequirement")
        or requirement.get("title")
        or ""
    )


def _intent(context: dict[str, Any]) -> dict[str, Any]:
    requirement = context.get("requirement") or {}
    return {
        "title": requirement.get("title"),
        "businessGoals": requirement.get("businessGoals") or [],
        "functionalRequirements": requirement.get("functionalRequirements") or [],
        "acceptanceCriteria": requirement.get("acceptanceCriteria") or [],
        "actors": requirement.get("actors") or [],
    }


def _repository(context: dict[str, Any]) -> dict[str, Any]:
    repository = context.get("repository") or {}
    return {
        "mode": repository.get("mode"),
        "repositoryId": repository.get("repositoryId"),
        "snapshotVersion": repository.get("repositorySnapshotVersion"),
        "affectedModules": repository.get("affectedModules") or [],
        "services": repository.get("services") or [],
        "apiEndpoints": repository.get("apiEndpoints") or [],
        "files": list(repository.get("files") or [])[:12],
        "warnings": repository.get("warnings") or [],
    }


def _knowledge(context: dict[str, Any]) -> dict[str, Any]:
    project_intelligence = context.get("projectIntelligence") or {}
    return {
        "documentation": list(context.get("relevantDocumentation") or [])[:8],
        "memory": list((context.get("engineeringMemory") or {}).get("matches") or [])[:10],
        "similarWork": list((context.get("similarWork") or {}).get("matches") or [])[:10],
        "architecture": context.get("architecture") or {},
        "projectBackground": project_intelligence.get("project") or {},
        "knowledgeRegistry": project_intelligence.get("knowledge") or {},
        "approvedProjectArtifacts": list(
            project_intelligence.get("approvedArtifacts") or []
        )[:10],
    }


def _boundaries(context: dict[str, Any]) -> dict[str, Any]:
    requirement = context.get("requirement") or {}
    project_intelligence = context.get("projectIntelligence") or {}
    rejected = (
        context.get("rejectedContext")
        or project_intelligence.get("rejectedContext")
        or []
    )
    return {
        "constraints": requirement.get("constraints") or [],
        "dependencies": context.get("dependencies") or {},
        "readiness": context.get("readiness") or {},
        "rejectedContextCount": len(rejected),
        "rejectedContextPolicy": "Excluded before reasoning; details remain in diagnostics.",
    }


def _validation(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "impact": context.get("impact") or {},
        "risks": (context.get("impact") or {}).get("potentialRisks") or [],
        "warnings": (context.get("repository") or {}).get("warnings") or [],
    }


def _evidence_catalog(context: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    repository = context.get("repository") or {}
    for module in repository.get("modules") or []:
        output.append(_evidence("module", module, "repository"))
    for item in repository.get("files") or []:
        name = (item.get("path") or item.get("name")) if isinstance(item, dict) else item
        output.append(_evidence("file", name, "repository"))
    for item in (context.get("azureDevOps") or {}).get("existingPlanning") or []:
        if isinstance(item, dict):
            output.append(_evidence("work-item", item.get("id") or item.get("workItemId"), "azure_devops", item.get("title")))
    for item in (context.get("engineeringMemory") or {}).get("matches") or []:
        if isinstance(item, dict):
            output.append(_evidence("memory", item.get("id"), "engineering_memory", item.get("title")))
    project_intelligence = context.get("projectIntelligence") or {}
    knowledge = project_intelligence.get("knowledge") or {}
    for module in knowledge.get("modules") or []:
        output.append(_evidence("module", module, "knowledge_registry"))
    for flow in knowledge.get("flows") or []:
        output.append(_evidence("flow", flow, "knowledge_registry"))
    for item in project_intelligence.get("approvedArtifacts") or []:
        if isinstance(item, dict):
            output.append(_evidence(
                "artifact", item.get("id"), "project_intelligence", item.get("title"),
            ))
    output.append(_evidence("context", context.get("contextId") or context.get("contextVersion"), "engineering_context"))
    unique: dict[str, dict[str, Any]] = {}
    for item in output:
        if item["referenceId"] and item["referenceId"] not in unique:
            unique[item["referenceId"]] = item
    return list(unique.values())[:60]


def _evidence(kind: str, value: Any, source: str, name: Any = "") -> dict[str, Any]:
    clean = str(value or "").strip()
    reference = f"{kind}:{clean}"
    return {"referenceId": reference, "source": source, "name": str(name or clean)}


def _output_schema(workflow_type: str) -> dict[str, Any]:
    if _key(workflow_type) == "planning_recommendation":
        option = {
            "strategy": "one supported recommendation strategy",
            "description": "string",
            "pros": ["string"],
            "cons": ["string"],
            "estimatedEffort": "bounded engineering-day range",
            "risks": ["string"],
            "reuseScore": 0,
            "confidence": 0,
        }
        return {
            "recommendation": option,
            "reasoning": ["string"],
            "alternatives": [option, option, option],
            "evidence": [{"referenceId": "string", "reason": "string"}],
            "risks": ["string"],
            "tradeOffs": ["string"],
            "impact": {},
            "confidence": 0,
        }
    return {
        "recommendation": {},
        "reasoning": ["string"],
        "alternatives": [{"title": "string", "reason": "string"}],
        "evidence": [{"referenceId": "string", "reason": "string"}],
        "risks": ["string"],
        "tradeOffs": ["string"],
        "impact": {},
        "confidence": 0,
    }


def _prompt_version(request: ReasoningRequest, provider: str, model: str) -> str:
    source = "|".join([
        PROMPT_VERSION,
        _key(request.workflowType),
        str(request.engineeringContext.get("contextVersion") or request.engineeringContext.get("contextId")),
        provider,
        model,
    ])
    return f"{PROMPT_VERSION}:{hashlib.sha256(source.encode()).hexdigest()[:12]}"


def _key(value: str) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", " ").split())
