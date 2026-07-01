"""Prompt section factory for Developer Prompt V2."""

from __future__ import annotations

from typing import Any

from backend.prompt_budget import PromptSection, estimateTokens

from .developer_prompt_model import clean, string_list
from .prompt_safety_rules import DEFAULT_DO_NOT_TOUCH, OUTPUT_REQUIREMENTS


def developer_prompt_sections(execution_package: dict[str, Any]) -> list[PromptSection]:
    business = _mapping(execution_package.get("businessContext"))
    boundary = _mapping(execution_package.get("implementationBoundary"))
    repository = _mapping(execution_package.get("repositoryContext"))
    readiness = _mapping(execution_package.get("readiness"))
    diagnostics = _mapping(execution_package.get("diagnostics"))
    dna = _mapping(execution_package.get("engineeringDNA"))
    acceptance = [item for item in execution_package.get("acceptanceMapping", []) if isinstance(item, dict)]
    standards = [item for item in execution_package.get("engineeringRules", []) if isinstance(item, dict)]
    risks = [item for item in execution_package.get("risks", []) if isinstance(item, dict)]
    tests = [item for item in execution_package.get("suggestedTests", []) if isinstance(item, dict)]

    sections = [
        _section(
            "role",
            "Role",
            "You are a senior software engineer working inside the existing codebase.",
            required=True,
            priority=100,
            source="instructions",
            compressible=False,
        ),
        _section(
            "objective",
            "Objective",
            _objective(execution_package, business),
            required=True,
            priority=100,
            source="instructions",
            compressible=True,
        ),
        _section(
            "current_work_item",
            "Task Context",
            {
                "taskId": execution_package.get("taskId"),
                "taskTitle": business.get("taskObjective") or clean(execution_package.get("taskTitle")),
                "taskObjective": business.get("taskObjective"),
                "taskScope": boundary.get("inScope", [])[:4],
                "taskDNAVersion": execution_package.get("dnaVersion"),
                "packageId": execution_package.get("packageId"),
            },
            required=True,
            priority=100,
            source="instructions",
            compressible=False,
        ),
        _section(
            "current_intent",
            "Parent Story Context",
            {
                "storyId": execution_package.get("storyId"),
                "storyTitle": business.get("storyTitle"),
                "storyUserGoal": business.get("storyUserGoal"),
                "relevantAcceptanceCriteria": [_compact_acceptance(item) for item in acceptance],
            },
            required=True,
            priority=95,
            source="instructions",
            compressible=False,
        ),
        _section(
            "dna",
            "Engineering DNA",
            {
                "dnaId": dna.get("dnaId"),
                "dnaVersion": dna.get("dnaVersion"),
                "capability": dna.get("capability"),
                "responsibilities": dna.get("responsibilities", []),
                "inScope": dna.get("inScope", []),
                "outOfScope": dna.get("outOfScope", []),
                "repositoryEvidence": dna.get("repositoryEvidence", {}),
            },
            required=True,
            priority=94,
            source="instructions",
            compressible=False,
        ),
        _section(
            "validation",
            "Acceptance Criteria Mapping",
            [_compact_acceptance(item) for item in acceptance],
            required=True,
            priority=95,
            source="validation",
            compressible=True,
        ),
        _section(
            "planning_boundary",
            "Implementation Boundary",
            {
                "inScope": string_list(boundary.get("inScope")),
                "outOfScope": string_list(boundary.get("outOfScope")),
                "allowedModules": string_list(boundary.get("allowedModules")),
                "blockedModules": string_list(boundary.get("blockedModules")),
                "allowedFlows": string_list(boundary.get("allowedFlows")),
                "blockedFlows": string_list(boundary.get("blockedFlows")),
                "assumptions": string_list(boundary.get("assumptions")),
                "constraints": string_list(boundary.get("constraints")),
            },
            required=True,
            priority=92,
            source="knowledge",
            compressible=True,
        ),
        _section(
            "repository_evidence",
            "Repository Context",
            {
                "fileRankingStatus": repository.get("fileRankingStatus"),
                "files": [_repo_item(item) for item in repository.get("relevantFiles", []) if isinstance(item, dict)][:8],
                "services": [_repo_item(item) for item in repository.get("relevantServices", []) if isinstance(item, dict)][:6],
                "apis": [_repo_item(item) for item in repository.get("relevantAPIs", []) if isinstance(item, dict)][:6],
                "modules": [_repo_item(item) for item in repository.get("relevantModules", []) if isinstance(item, dict)][:6],
                "flows": [_repo_item(item) for item in repository.get("relevantFlows", []) if isinstance(item, dict)][:6],
            },
            required=True,
            priority=88,
            source="repository",
            compressible=True,
        ),
        _section(
            "knowledge_summary",
            "Engineering Standards",
            [_standard_item(item) for item in standards][:10],
            required=True,
            priority=80,
            source="knowledge",
            compressible=True,
        ),
        _section(
            "risks",
            "Risks",
            [_risk_item(item) for item in risks][:8],
            required=False,
            priority=70,
            source="diagnostics",
            compressible=True,
        ),
        _section(
            "required_tests",
            "Required Tests",
            [_test_item(item) for item in tests][:10],
            required=True,
            priority=86,
            source="validation",
            compressible=True,
        ),
        _section(
            "instructions",
            "Output Requirements",
            OUTPUT_REQUIREMENTS,
            required=True,
            priority=100,
            source="instructions",
            compressible=False,
        ),
        _section(
            "output_schema",
            "Do Not Touch",
            _do_not_touch(boundary, repository, diagnostics),
            required=True,
            priority=100,
            source="instructions",
            compressible=False,
        ),
    ]
    return sections


def _section(
    section_id: str,
    name: str,
    content: Any,
    *,
    required: bool,
    priority: int,
    source: str,
    compressible: bool,
) -> PromptSection:
    return PromptSection(
        id=section_id,
        name=name,
        priority=priority,
        estimatedTokens=estimateTokens(str(content)),
        required=required,
        compressible=compressible,
        source=source,
        content=content,
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _objective(package: dict[str, Any], business: dict[str, Any]) -> str:
    task = clean(business.get("taskObjective")) or "Implement the selected task."
    value = clean(business.get("businessValue"))
    capability = clean(business.get("featureCapability"))
    parts = [task]
    if capability:
        parts.append(f"Stay within the approved capability: {capability}.")
    if value:
        parts.append(f"Preserve the expected outcome: {value}.")
    parts.append("Do not regenerate planning artifacts; implement the approved execution package.")
    return "\n".join(parts[:4])


def _compact_acceptance(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("acceptanceCriteriaId"),
        "text": clean(item.get("acceptanceText")),
        "implementation": clean(item.get("implementationArea")),
        "validation": clean(item.get("validationExpectation")),
    }


def _repo_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": clean(item.get("name")),
        "type": clean(item.get("type")),
        "confidence": item.get("confidence"),
        "reason": clean(item.get("reason")),
    }


def _standard_item(item: dict[str, Any]) -> str:
    return clean(item.get("rule") or item.get("name") or item.get("title"))


def _risk_item(item: dict[str, Any]) -> str:
    return clean(item.get("risk") or item.get("title") or item.get("name"))


def _test_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": clean(item.get("type")),
        "title": clean(item.get("title")),
        "coverage": string_list(item.get("coverage")),
        "priority": clean(item.get("priority")),
    }


def _do_not_touch(boundary: dict[str, Any], repository: dict[str, Any], diagnostics: dict[str, Any]) -> list[str]:
    rules = list(DEFAULT_DO_NOT_TOUCH)
    for module in string_list(boundary.get("blockedModules")):
        rules.append(f"Do not modify {module}.")
    if clean(repository.get("fileRankingStatus")) == "Repository file ranking not available":
        rules.append("Repository file ranking not available. Do not invent file paths. Locate the closest existing implementation before editing.")
    return rules
