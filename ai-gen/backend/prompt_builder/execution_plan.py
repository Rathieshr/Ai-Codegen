"""Execution Plan builder.

The Execution Plan is the primary AI-assistant handoff. It consumes only
Execution Package V2 and turns it into a compact, platform-agnostic plan.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.prompt_budget import PromptSection, budgetProfileForProvider, buildPrompt, estimateTokens

from .developer_prompt_diagnostics import developer_prompt_diagnostics
from .developer_prompt_model import clean, now_iso, string_list
from .prompt_safety_rules import DEFAULT_DO_NOT_TOUCH, OUTPUT_REQUIREMENTS


EXECUTION_MODES: dict[str, dict[str, str]] = {
    "implement": {
        "label": "Implement",
        "guidance": "Focus on building the approved behavior with minimal safe changes and tests.",
    },
    "review_existing_code": {
        "label": "Review Existing Code",
        "guidance": "Analyze the existing implementation against the package. Identify gaps before proposing changes.",
    },
    "refactor": {
        "label": "Refactor",
        "guidance": "Preserve behavior while improving structure. Keep changes small, reversible, and covered by regression tests.",
    },
    "bug_fix": {
        "label": "Bug Fix",
        "guidance": "Start with root-cause analysis, make the smallest corrective change, and prevent regression.",
    },
    "spike_investigation": {
        "label": "Spike / Investigation",
        "guidance": "Investigate options, evidence, and risks. Document findings before recommending implementation.",
    },
}


def build_execution_plan(
    execution_package: dict[str, Any],
    *,
    execution_mode: str = "implement",
    provider: str = "azure_phi",
    model: str = "",
    context_limit_override: int | None = None,
) -> dict[str, Any]:
    package = execution_package if isinstance(execution_package, dict) else {}
    package_id = clean(package.get("packageId")) or f"execpkg_{_stable_hash(package)[:12]}"
    mode = normalize_execution_mode(execution_mode)
    sections = execution_plan_sections(package, mode)
    profile = budgetProfileForProvider(
        provider or "azure_phi",
        model or "",
        operation="build_execution_plan",
        context_limit_override=context_limit_override,
    )
    budget_result = buildPrompt(sections, profile)
    optimized_sections = budget_result.get("sections") if isinstance(budget_result.get("sections"), list) else sections
    final_plan = format_execution_plan(optimized_sections, mode)
    warnings = _warnings(package, budget_result, mode)
    diagnostics = developer_prompt_diagnostics(
        budget_result=budget_result,
        warnings=warnings,
        section_count=len(optimized_sections),
        package_id=package_id,
    )
    diagnostics["executionMode"] = mode
    diagnostics["executionModeLabel"] = EXECUTION_MODES[mode]["label"]
    estimated_tokens = estimateTokens(final_plan)
    diagnostics["finalPlanTokens"] = estimated_tokens
    return {
        "planId": f"execplan_{_stable_hash({'packageId': package_id, 'mode': mode, 'plan': final_plan})[:12]}",
        "packageId": package_id,
        "taskId": package.get("taskId"),
        "storyId": package.get("storyId"),
        "artifactId": package.get("artifactId") or package.get("taskId") or package.get("storyId"),
        "artifactType": clean(package.get("artifactType")) or ("Task" if package.get("taskId") else "Story"),
        "executionMode": mode,
        "executionModeLabel": EXECUTION_MODES[mode]["label"],
        "providerProfile": diagnostics.get("promptBudgetProfile") or profile.compression_strategy,
        "sections": [section.to_dict() for section in optimized_sections],
        "finalPlan": final_plan,
        "plan": final_plan,
        "prompt": final_plan,
        "estimatedTokens": estimated_tokens,
        "warnings": warnings,
        "diagnostics": diagnostics,
        "generatedAt": now_iso(),
    }


def normalize_execution_mode(value: str) -> str:
    key = clean(value).replace("-", "_").replace(" ", "_").replace("/", "_").casefold()
    aliases = {
        "": "implement",
        "implementation": "implement",
        "review": "review_existing_code",
        "review_code": "review_existing_code",
        "existing_code_review": "review_existing_code",
        "bug": "bug_fix",
        "fix": "bug_fix",
        "spike": "spike_investigation",
        "investigation": "spike_investigation",
    }
    key = aliases.get(key, key)
    return key if key in EXECUTION_MODES else "implement"


def execution_plan_sections(package: dict[str, Any], execution_mode: str = "implement") -> list[PromptSection]:
    business = _mapping(package.get("businessContext"))
    boundary = _mapping(package.get("implementationBoundary"))
    repository = _mapping(package.get("repositoryContext"))
    readiness = _mapping(package.get("readiness"))
    acceptance = [item for item in package.get("acceptanceMapping", []) if isinstance(item, dict)]
    standards = [item for item in package.get("engineeringRules", []) if isinstance(item, dict)]
    risks = [item for item in package.get("risks", []) if isinstance(item, dict)]
    tests = [item for item in package.get("suggestedTests", []) if isinstance(item, dict)]
    ui_guidance = _ui_guidance(boundary, repository, acceptance)
    mode = normalize_execution_mode(execution_mode)

    return [
        _section("role", "Role", "You are a senior software engineer working inside the existing codebase.", True, 100, "instructions", False),
        _section("objective", "Execution Mode", _mode_content(mode), True, 100, "instructions", False),
        _section("current_work_item", "Context", _context(package, business, readiness), True, 100, "instructions", False),
        _section("current_intent", "Implementation Goal", _implementation_goal(business, mode), True, 98, "instructions", True),
        _section("repository_evidence", "Repository Context", _repository_context(repository), True, 90, "repository", True),
        _section("validation", "Acceptance Criteria", [_acceptance_item(item) for item in acceptance], True, 95, "validation", True),
        _section("planning_boundary", "Implementation Boundary", _boundary(boundary), True, 92, "knowledge", True),
        _section("knowledge_summary", "Engineering Standards", [_standard_item(item) for item in standards], True, 82, "knowledge", True),
        _section("ui_guidance", "UI Guidance", ui_guidance, False, 72, "knowledge", True),
        _section("required_tests", "Testing Guidance", [_test_item(item) for item in tests], True, 86, "validation", True),
        _section("risks", "Risk Notes", [_risk_item(item) for item in risks], False, 68, "diagnostics", True),
        _section("instructions", "Validation Checklist", _validation_checklist(boundary), True, 100, "instructions", False),
        _section("output_schema", "Output Instructions", _output_instructions(mode, boundary), True, 100, "instructions", False),
    ]


def format_execution_plan(sections: list[PromptSection], execution_mode: str = "implement") -> str:
    section_map = {section.id: section for section in sections}
    ordered_ids = [
        "current_work_item",
        "objective",
        "current_intent",
        "repository_evidence",
        "validation",
        "planning_boundary",
        "knowledge_summary",
        "ui_guidance",
        "required_tests",
        "risks",
        "instructions",
        "output_schema",
    ]
    parts = [
        "# Execution Plan",
        "",
        f"Mode: {EXECUTION_MODES[normalize_execution_mode(execution_mode)]['label']}",
        "",
    ]
    for section_id in ordered_ids:
        section = section_map.get(section_id)
        if not section:
            continue
        content = _format_section(section.id, section.content)
        if not clean(content):
            continue
        if section.id == "ui_guidance" and "No UI-specific changes" in content:
            continue
        parts.append(f"## {section.name}")
        parts.append(content)
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def _section(section_id: str, name: str, content: Any, required: bool, priority: int, source: str, compressible: bool) -> PromptSection:
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


def _context(package: dict[str, Any], business: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "businessGoal": clean(business.get("epicBusinessGoal")),
        "businessValue": clean(business.get("businessValue")),
        "storyObjective": clean(business.get("storyUserGoal")),
        "taskObjective": clean(business.get("taskObjective")),
        "repositorySnapshotVersion": clean(package.get("repositorySnapshotVersion")),
        "knowledgeVersion": clean(package.get("knowledgeVersion")),
        "executionReadiness": readiness.get("status") or clean(package.get("execution_readiness")) or "Needs Review",
        "readinessScore": readiness.get("executionReadinessScore") or package.get("execution_readiness_score"),
    }


def _mode_content(mode: str) -> dict[str, str]:
    mode_info = EXECUTION_MODES[mode]
    return {"mode": mode_info["label"], "guidance": mode_info["guidance"]}


def _implementation_goal(business: dict[str, Any], mode: str) -> str:
    task = clean(business.get("taskObjective")) or "Complete the approved execution package."
    story = clean(business.get("storyUserGoal"))
    parts = [task]
    if story:
        parts.append(f"Support the parent story goal: {story}.")
    parts.append(EXECUTION_MODES[mode]["guidance"])
    return " ".join(parts)


def _repository_context(repository: dict[str, Any]) -> dict[str, Any]:
    files = [_repo_item(item) for item in repository.get("relevantFiles", []) if isinstance(item, dict)][:8]
    return {
        "fileRankingStatus": clean(repository.get("fileRankingStatus")),
        "files": files,
        "services": [_repo_item(item) for item in repository.get("relevantServices", []) if isinstance(item, dict)][:6],
        "apis": [_repo_item(item) for item in repository.get("relevantAPIs", []) if isinstance(item, dict)][:6],
        "modules": [_repo_item(item) for item in repository.get("relevantModules", []) if isinstance(item, dict)][:6],
        "flows": [_repo_item(item) for item in repository.get("relevantFlows", []) if isinstance(item, dict)][:6],
        "dependencies": [_repo_item(item) for item in repository.get("dependencies", []) if isinstance(item, dict)][:6],
    }


def _repo_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": clean(item.get("name") or item.get("path")),
        "type": clean(item.get("type")),
        "confidence": item.get("confidence"),
        "reason": clean(item.get("reason")),
        "evidence": string_list(item.get("evidence"))[:2],
        "source": clean(item.get("source")),
    }


def _acceptance_item(item: dict[str, Any]) -> dict[str, str]:
    return {
        "id": clean(item.get("acceptanceCriteriaId")) or "AC",
        "text": clean(item.get("acceptanceText")),
        "implementation": clean(item.get("implementationArea")),
        "validation": clean(item.get("validationExpectation")),
    }


def _boundary(boundary: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "inScope": string_list(boundary.get("inScope")),
        "outOfScope": string_list(boundary.get("outOfScope")),
        "allowedModules": string_list(boundary.get("allowedModules")),
        "blockedModules": string_list(boundary.get("blockedModules")),
        "allowedFlows": string_list(boundary.get("allowedFlows")),
        "blockedFlows": string_list(boundary.get("blockedFlows")),
        "assumptions": string_list(boundary.get("assumptions")),
        "constraints": string_list(boundary.get("constraints")),
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


def _ui_guidance(boundary: dict[str, Any], repository: dict[str, Any], acceptance: list[dict[str, Any]]) -> list[str]:
    text = " ".join(
        [
            " ".join(string_list(boundary.get("inScope"))),
            " ".join(string_list(boundary.get("allowedModules"))),
            " ".join(string_list(boundary.get("allowedFlows"))),
            " ".join(clean(item.get("acceptanceText")) for item in acceptance),
            " ".join(clean(item.get("name") or item.get("type")) for item in repository.get("relevantFiles", []) if isinstance(item, dict)),
        ]
    ).casefold()
    if not any(keyword in text for keyword in ["ui", "screen", "view", "page", "xaml", "component", "dashboard", "mobile", "frontend"]):
        return ["No UI-specific changes identified from the execution package."]
    return [
        "Preserve existing component patterns and visual states.",
        "Cover loading, error, empty, and permission states when UI is touched.",
        "Keep accessibility and responsive behavior aligned with project standards.",
    ]


def _validation_checklist(boundary: dict[str, Any]) -> list[str]:
    rules = [
        "Acceptance criteria are satisfied and traceable to implementation.",
        "No unrelated files or modules are changed.",
        "Repository alignment from the execution package is preserved.",
        "Architecture and engineering standards are respected.",
        "Required tests are added or updated.",
    ]
    for module in string_list(boundary.get("blockedModules")):
        rules.append(f"Blocked module remains untouched: {module}.")
    return rules


def _output_instructions(mode: str, boundary: dict[str, Any]) -> list[str]:
    instructions = list(OUTPUT_REQUIREMENTS)
    if mode == "review_existing_code":
        instructions.insert(0, "Review first. Report alignment, gaps, and risks before suggesting edits.")
    if mode == "refactor":
        instructions.insert(0, "Preserve behavior. Do not expand scope while improving structure.")
    if mode == "bug_fix":
        instructions.insert(0, "Identify root cause before editing and add regression coverage.")
    if mode == "spike_investigation":
        instructions.insert(0, "Produce findings, options, tradeoffs, and recommended next steps before implementation.")
    instructions.extend(DEFAULT_DO_NOT_TOUCH)
    for module in string_list(boundary.get("blockedModules")):
        instructions.append(f"Do not modify {module}.")
    return instructions


def _format_section(section_id: str, content: Any) -> str:
    if section_id in {"current_work_item", "objective"}:
        return _key_values(content)
    if section_id == "repository_evidence":
        return _repository_lines(content)
    if section_id == "validation":
        return _acceptance_lines(content)
    if section_id == "planning_boundary":
        return _boundary_lines(content)
    if section_id == "knowledge_summary":
        return _list_lines(content, "Follow existing codebase standards.")
    if section_id == "ui_guidance":
        return _list_lines(content, "")
    if section_id == "required_tests":
        return _test_lines(content)
    if section_id in {"risks", "instructions", "output_schema"}:
        return _list_lines(content, "No additional notes.")
    if isinstance(content, str):
        return content
    return _key_values(content)


def _key_values(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return _list_lines(content, "")
    lines = []
    for key, value in content.items():
        if value in ("", None, [], {}):
            continue
        label = "".join([" " + char if char.isupper() else char for char in str(key)]).strip().title()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _repository_lines(content: Any) -> str:
    data = content if isinstance(content, dict) else {}
    lines: list[str] = []
    files = data.get("files") if isinstance(data.get("files"), list) else []
    if files:
        lines.append("- Relevant files:")
        for item in files:
            if isinstance(item, dict):
                confidence = item.get("confidence")
                suffix = f" confidence={confidence}" if confidence not in ("", None) else ""
                evidence = string_list(item.get("evidence"))
                evidence_text = f" Evidence: {', '.join(evidence)}." if evidence else ""
                lines.append(f"  - {clean(item.get('name'))} ({clean(item.get('type')) or 'file'}{suffix}): {clean(item.get('reason'))}.{evidence_text}")
        status = clean(data.get("fileRankingStatus"))
        if status:
            lines.append(f"- Repository file ranking: {status}")
    else:
        lines.append("- Repository file ranking not available. Do not invent file paths. Locate the closest existing implementation before editing.")
    for key, label in [("services", "Services"), ("apis", "APIs"), ("modules", "Modules"), ("flows", "Flows"), ("dependencies", "Dependencies")]:
        values = data.get(key) if isinstance(data.get(key), list) else []
        if values:
            lines.append(f"- {label}:")
            for item in values[:6]:
                if isinstance(item, dict):
                    lines.append(f"  - {clean(item.get('name'))}: {clean(item.get('reason'))}")
    return "\n".join(lines)


def _acceptance_lines(content: Any) -> str:
    items = content if isinstance(content, list) else []
    if not items:
        return "No acceptance criteria mapping available. Stop and clarify before implementation."
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f"- {clean(item.get('id'))}: {clean(item.get('text'))}")
            lines.append(f"  - Implementation expectation: {clean(item.get('implementation')) or 'Map this AC to the implementation.'}")
            lines.append(f"  - Validation expectation: {clean(item.get('validation')) or 'Add validation for this AC.'}")
    return "\n".join(lines)


def _boundary_lines(content: Any) -> str:
    data = content if isinstance(content, dict) else {}
    lines: list[str] = []
    for label, key in [
        ("In scope", "inScope"),
        ("Out of scope", "outOfScope"),
        ("Allowed modules", "allowedModules"),
        ("Blocked modules", "blockedModules"),
        ("Allowed flows", "allowedFlows"),
        ("Blocked flows", "blockedFlows"),
        ("Assumptions", "assumptions"),
        ("Constraints", "constraints"),
    ]:
        values = data.get(key) if isinstance(data.get(key), list) else []
        if values:
            lines.append(f"- {label}:")
            lines.extend(f"  - {clean(item)}" for item in values if clean(item))
    return "\n".join(lines) or "- Use only the approved execution package boundary."


def _test_lines(content: Any) -> str:
    items = content if isinstance(content, list) else []
    if not items:
        return "- Add unit, integration, negative, permission, and regression tests for the mapped acceptance criteria."
    lines = []
    for item in items:
        if isinstance(item, dict):
            coverage = string_list(item.get("coverage"))
            suffix = f" Covers: {', '.join(coverage)}." if coverage else ""
            lines.append(f"- {clean(item.get('type')).title() or 'Test'}: {clean(item.get('title'))}.{suffix}")
    return "\n".join(lines)


def _list_lines(content: Any, empty: str) -> str:
    if isinstance(content, list):
        values = []
        for item in content:
            if isinstance(item, dict):
                values.append(clean(item.get("rule") or item.get("risk") or item.get("title") or item.get("name")))
            else:
                values.append(clean(item))
        values = [value for value in values if value]
        return "\n".join(f"- {value}" for value in values) if values else empty
    values = string_list(content)
    return "\n".join(f"- {value}" for value in values) if values else empty


def _warnings(package: dict[str, Any], budget_result: dict[str, Any], mode: str) -> list[str]:
    warnings: list[str] = []
    repository = _mapping(package.get("repositoryContext"))
    if not repository.get("relevantFiles"):
        warnings.append("Repository file ranking not available. Do not invent file paths.")
    readiness = _mapping(package.get("readiness"))
    if readiness.get("status") in {"Needs Review", "Blocked"}:
        warnings.append(f"Execution readiness is {readiness.get('status')}. Review blockers before proceeding.")
    diagnostics = budget_result.get("diagnostics") if isinstance(budget_result.get("diagnostics"), dict) else {}
    if diagnostics.get("blockedByBudgetGuard"):
        warnings.append("Execution Plan exceeded provider budget after compression. Review diagnostics before using.")
    if diagnostics.get("compressionApplied"):
        warnings.append("Execution Plan sections were compressed for the selected provider budget.")
    if mode == "spike_investigation":
        warnings.append("Spike mode should produce findings before implementation changes.")
    return warnings


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
