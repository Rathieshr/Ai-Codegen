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
        context = _validate_context(request.engineeringContext, request.workflowType)
        template = resolve_template(request.workflowType)
        catalog = _evidence_catalog(context)
        if _key(request.workflowType) in {"requirement_refinement", "requirement_intent_analysis"}:
            return _build_requirement_intent_prompt(
                request, context, template, catalog, provider, model,
            )
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


def _validate_context(value: Any, workflow_type: str = "") -> dict[str, Any]:
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
    bounded_type = {
        "requirement_refinement": "RequirementRefinementInput",
        "requirement_intent_analysis": "RequirementIntentInput",
    }.get(_key(workflow_type))
    if bounded_type:
        if value.get("contextType") != bounded_type:
            raise ValueError(f"{workflow_type} requires bounded {bounded_type}.")
        return value
    if not value.get("contextId") and not value.get("contextVersion"):
        raise ValueError("EngineeringContext must include contextId or contextVersion.")
    return value


def _build_requirement_intent_prompt(
    request: ReasoningRequest,
    context: dict[str, Any],
    template: Any,
    catalog: list[dict[str, Any]],
    provider: str,
    model: str,
) -> BuiltReasoningPrompt:
    profile = budgetProfileForProvider(
        provider or "deterministic", model, operation=f"reason_{_key(request.workflowType)}",
    )
    small_model = profile.context_limit <= 2000
    sections = [
        _section("role", "Role", template.role, True, 100, False, "template"),
        _section("objective", "Objective", template.objective, True, 100, False, "template"),
        _section(
            "current_work_item", "Current Requirement",
            request.userRequirement or context.get("requirement") or {},
            True, 100, True, "requirement",
        ),
        _section(
            "bounded_metadata", "Bounded Project Metadata",
            context.get("metadata") or {}, False, 65, True, "project_metadata",
        ),
        _section(
            "instructions", "Instructions",
            _compact_requirement_instructions(request.workflowType)
            if small_model else list(template.instructions),
            True, 100, False, "template",
        ),
        _section(
            "output_schema", "Output Schema",
            _compact_requirement_schema(request.workflowType)
            if small_model else _output_schema(request.workflowType),
            True, 100, False, "schema",
        ),
    ]
    built = buildPrompt(sections, profile)
    return BuiltReasoningPrompt(
        prompt=str(built["prompt"]),
        promptVersion=_prompt_version(request, provider, model),
        sections=[item.to_dict() for item in built["sections"]],
        evidenceCatalog=catalog,
        diagnostics=dict(built["diagnostics"]),
    )


def _compact_requirement_instructions(workflow_type: str) -> list[str]:
    if _key(workflow_type) == "requirement_refinement":
        return [
            "Improve clarity while preserving the exact supplied intent and scope.",
            "Separate business outcome (why) from user intent (what).",
            "Extract actors, capabilities, entities, concepts, and search hints only from source terms.",
            "Do not invent features, rules, architecture, APIs, criteria, constraints, or dependencies.",
            "Identify unresolved ambiguity as clarificationCandidates.",
            "Use source:requirement as evidence and return only the JSON object.",
        ]
    return [
        "Interpret only the supplied requirement and bounded metadata.",
        "Separate business outcome from functional intent.",
        "Return search hints, not repository or Azure DevOps facts.",
        "Use source:requirement as evidence and return only the JSON object.",
    ]


def _compact_requirement_schema(workflow_type: str) -> dict[str, Any]:
    if _key(workflow_type) == "requirement_refinement":
        return {
            "recommendation": {"refinement": {
                "refinedRequirement": "string",
                "executiveSummary": "string",
                "businessGoal": "why/value, distinct from userIntent",
                "problemStatement": "string",
                "userIntent": "what the user needs",
                "primaryActor": "string or empty",
                "coreCapabilities": ["string"],
                "expectedOutcome": "string or empty",
                "businessEntities": ["string"],
                "engineeringConcepts": ["string"],
                "domainTerminology": ["string"],
                "repositorySearchHints": ["string"],
                "markdownSearchHints": ["string"],
                "azureDevOpsSearchHints": ["string"],
                "clarificationCandidates": ["string"],
                "confidence": 0,
            }},
            "reasoning": ["string"],
            "alternatives": [],
            "evidence": [{"referenceId": "source:requirement"}],
            "confidence": 0,
        }
    return _output_schema(workflow_type)


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
    document = requirement.get("analysisDocument") or {}
    return {
        "title": requirement.get("title"),
        "businessGoals": [document.get("businessGoal")] if document.get("businessGoal") else requirement.get("businessGoals") or [],
        "functionalRequirements": document.get("functionalRequirements") or requirement.get("functionalRequirements") or [],
        "acceptanceCriteria": document.get("acceptanceCriteria") or requirement.get("acceptanceCriteria") or [],
        "actors": [value for value in [document.get("primaryActor"), *(document.get("secondaryActors") or [])] if value] or requirement.get("actors") or [],
        "capabilities": document.get("capabilities") or [],
        "canonicalRequirementAnalysis": document,
        "requirementIntent": requirement.get("requirementIntent") or {},
        "intentPolicy": "Interpretation and search hints only; not engineering fact.",
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
    markdown = context.get("repository_markdown_context") or {}
    synthesis = context.get("knowledge_synthesis") or {}
    return {
        "documentation": list(context.get("relevantDocumentation") or [])[:8],
        "repositoryMarkdown": [
            {
                "evidenceId": item.get("evidenceId"),
                "path": item.get("path"),
                "heading": item.get("heading"),
                "classification": item.get("classification"),
                "authority": item.get("authority"),
                "factualStatus": item.get("factualStatus") or "usable",
                "statements": (
                    (item.get("statements") or {})
                    if item.get("factualStatus") != "conflicted"
                    else {}
                ),
                "sourceText": (
                    item.get("sourceText")
                    if item.get("factualStatus") != "conflicted"
                    else "Claim withheld because repository sources conflict."
                ),
                "repositoryRevision": item.get("repositoryRevision"),
                "contentHash": item.get("contentHash"),
                "selectionReason": item.get("selectionReason"),
            }
            for item in list(markdown.get("selected") or [])[:12]
        ],
        "memory": list((context.get("engineeringMemory") or {}).get("matches") or [])[:10],
        "similarWork": list((context.get("similarWork") or {}).get("matches") or [])[:10],
        "architecture": context.get("architecture") or {},
        "projectBackground": project_intelligence.get("project") or {},
        "knowledgeRegistry": project_intelligence.get("knowledge") or {},
        "approvedProjectArtifacts": list(
            project_intelligence.get("approvedArtifacts") or []
        )[:10],
        "sourceAuthority": synthesis.get("authorityRules") or {},
        "sourceConflicts": list(synthesis.get("conflicts") or [])[:20],
        "knowledgeLineage": context.get("sourceVersions") or {},
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
        "sourceConflicts": list(
            (context.get("knowledge_synthesis") or {}).get("conflicts") or []
        )[:20],
        "conflictPolicy": "Do not treat a conflicted claim as fact until it is resolved.",
    }


def _validation(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "impact": context.get("impact") or {},
        "risks": (context.get("impact") or {}).get("potentialRisks") or [],
        "warnings": (context.get("repository") or {}).get("warnings") or [],
        "knowledgeConflicts": list(
            (context.get("repository_markdown_context") or {}).get("conflicts") or []
        )[:20],
    }


def _evidence_catalog(context: dict[str, Any]) -> list[dict[str, Any]]:
    if context.get("contextType") in {"RequirementRefinementInput", "RequirementIntentInput"}:
        requirement = context.get("requirement") or {}
        return [{
            "referenceId": "source:requirement",
            "source": "requirement",
            "name": str(requirement.get("title") or "Current Requirement"),
        }]
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
    for item in (context.get("repository_markdown_context") or {}).get("selected") or []:
        if isinstance(item, dict):
            output.append({
                "referenceId": str(item.get("evidenceId") or ""),
                "source": "repository_markdown",
                "name": f"{item.get('path') or ''}#{item.get('heading') or ''}",
                "path": item.get("path"),
                "heading": item.get("heading"),
                "authority": item.get("authority"),
                "repositoryRevision": item.get("repositoryRevision"),
                "contentHash": item.get("contentHash"),
            })
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
    workflow_key = _key(workflow_type)
    if workflow_key == "requirement_refinement":
        return {
            "recommendation": {
                "refinement": {
                    "refinedRequirement": "string",
                    "executiveSummary": "string",
                    "requirementSummary": "string",
                    "businessGoal": "string distinct from userIntent",
                    "businessObjective": "string",
                    "problemStatement": "string",
                    "userIntent": "string",
                    "primaryActor": "string or empty",
                    "secondaryActors": ["string"],
                    "coreCapability": "string",
                    "coreCapabilities": ["string"],
                    "expectedOutcome": "string",
                    "businessEntities": ["string"],
                    "engineeringConcepts": ["string"],
                    "domainTerminology": ["string"],
                    "repositorySearchHints": ["string"],
                    "markdownSearchHints": ["string"],
                    "azureDevOpsSearchHints": ["string"],
                    "possibleModuleNames": ["string"],
                    "possibleFeatureNames": ["string"],
                    "potentialDomainTerms": ["string"],
                    "potentialSearchKeywords": ["string"],
                    "potentialRepositoryTerms": ["string"],
                    "potentialAzureDevOpsTerms": ["string"],
                    "potentialMarkdownTerms": ["string"],
                    "changes": [{"change": "string", "reason": "string"}],
                    "ambiguities": ["string"],
                    "clarificationCandidates": ["string"],
                    "requirementIntent": {
                        "businessGoal": "string",
                        "functionalIntent": ["string"],
                        "entities": ["string"],
                        "actions": ["string"],
                        "concepts": ["string"],
                        "keywords": ["string"],
                        "repositoryHints": ["string"],
                        "markdownHints": ["string"],
                        "azureDevOpsHints": ["string"],
                        "clarificationCandidates": ["string"],
                        "confidence": 0,
                    },
                    "confidence": 0,
                },
            },
            "reasoning": ["string"],
            "alternatives": [{"title": "string", "reason": "string"}],
            "evidence": [{"referenceId": "source:requirement", "reason": "string"}],
            "risks": ["string"],
            "tradeOffs": ["string"],
            "impact": {},
            "confidence": 0,
        }
    if workflow_key == "requirement_intent_analysis":
        return {
            "recommendation": {
                "requirementIntent": {
                    "intentSummary": "string",
                    "businessGoal": "string",
                    "functionalIntent": ["string"],
                    "entities": ["string"],
                    "primaryActor": "string",
                    "secondaryActors": ["string"],
                    "capabilities": ["string"],
                    "actions": ["string"],
                    "concepts": ["string"],
                    "businessTerminology": ["string"],
                    "explicitConstraints": ["string"],
                    "possibleAssumptions": ["string"],
                    "ambiguities": ["string"],
                    "riskIndicators": ["string"],
                    "technologyConcepts": ["string"],
                    "domainSynonyms": ["string"],
                    "searchKeywords": ["string"],
                    "possibleModuleNames": ["string"],
                    "possibleFeatureNames": ["string"],
                    "possibleApis": ["string"],
                    "possibleRepositoryTerms": ["string"],
                    "possibleAzureDevOpsSearchTerms": ["string"],
                    "possibleMarkdownSearchTerms": ["string"],
                    "clarificationCandidates": ["string"],
                    "confidence": 0,
                },
            },
            "reasoning": ["string"],
            "alternatives": [{"title": "string", "reason": "string"}],
            "evidence": [{"referenceId": "source:requirement", "reason": "string"}],
            "risks": ["string"],
            "tradeOffs": ["string"],
            "impact": {},
            "confidence": 0,
        }
    if workflow_key == "requirement_evidence_synthesis":
        return {
            "recommendation": {
                "executiveSummary": "string",
                "businessGoal": "string",
                "problemStatement": "string",
                "primaryActor": "string",
                "secondaryActors": ["string"],
                "businessValue": "string",
                "capabilities": ["string"],
                "functionalRequirements": ["string"],
                "suggestedEnhancements": [{"text": "string", "reason": "string"}],
                "candidateNonFunctionalRequirements": ["string"],
                "nonFunctionalRequirements": ["string"],
                "businessRules": ["string"],
                "constraints": ["string"],
                "dependencies": ["string"],
                "affectedModules": ["string"],
                "affectedServices": ["string"],
                "affectedApis": ["string"],
                "affectedScreens": ["string"],
                "repositoryFindings": ["string"],
                "markdownFindings": ["string"],
                "reusableComponents": ["string"],
                "architectureFindings": ["string"],
                "reuseOpportunities": ["string"],
                "affectedEngineeringElements": ["string"],
                "risks": ["string"],
                "assumptions": ["string"],
                "openQuestions": ["string"],
                "missingInformation": ["string"],
                "engineeringInsights": ["string"],
                "planningReadiness": "Ready | ReadyWithRecommendations | NeedsUserInput | Blocked",
            },
            "reasoning": ["string"],
            "alternatives": [{"title": "string", "reason": "string"}],
            "evidence": [{"referenceId": "string", "reason": "string"}],
            "risks": ["string"],
            "tradeOffs": ["string"],
            "impact": {},
            "confidence": 0,
        }
    if workflow_key == "acceptance_criteria_generation":
        return {
            "recommendation": {
                "acceptanceCriteria": [{
                    "title": "short scenario title",
                    "text": "Scenario: ...\\nGiven ...\\nWhen ...\\nThen ...",
                    "type": "Functional | Business Rule | Non-Functional",
                    "mappedFunctionalRequirement": "exact supplied functional requirement",
                    "confidence": 0,
                }],
                "summary": "string",
            },
            "reasoning": ["string"],
            "alternatives": [{"title": "string", "reason": "string"}],
            "evidence": [{"referenceId": "string", "reason": "string"}],
            "risks": ["string"],
            "tradeOffs": ["string"],
            "impact": {},
            "confidence": 0,
        }
    if workflow_key == "planning_recommendation":
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
    version = "requirement-refinement-v2" if _key(request.workflowType) == "requirement_refinement" else PROMPT_VERSION
    source = "|".join([
        version,
        _key(request.workflowType),
        str(request.engineeringContext.get("contextVersion") or request.engineeringContext.get("contextId")),
        provider,
        model,
    ])
    return f"{version}:{hashlib.sha256(source.encode()).hexdigest()[:12]}"


def _key(value: str) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", " ").split())
