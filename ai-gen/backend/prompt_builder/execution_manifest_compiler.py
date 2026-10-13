"""Adapt a deterministic CompiledPrompt into a provider-budgeted Execution Prompt.

Prompt section compilation belongs to ``backend.prompt_compiler``. This module
is the downstream compatibility adapter used by the legacy DeveloperPrompt
consumer; it may apply provider budgets and final presentation formatting.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.prompt_budget import PromptSection, budgetProfileForProvider, buildPrompt, estimateTokens
from backend.prompt_compiler import PromptCompiler

from .developer_prompt_diagnostics import developer_prompt_diagnostics
from .developer_prompt_model import clean, now_iso
from .prompt_output_formatter import format_developer_prompt, prompt_tokens


def compile_execution_manifest(
    execution_manifest: dict[str, Any],
    *,
    compiled_prompt: dict[str, Any] | None = None,
    budgeted_prompt: dict[str, Any] | None = None,
    provider: str = "azure_phi",
    model: str = "",
    context_limit_override: int | None = None,
) -> dict[str, Any]:
    """Apply the model-adaptation stage after deterministic prompt compilation."""

    manifest = execution_manifest if isinstance(execution_manifest, dict) else {}
    if not manifest.get("manifestId") or manifest.get("immutable") is not True:
        raise ValueError("An immutable Execution Manifest is required.")
    compiled = compiled_prompt if isinstance(compiled_prompt, dict) else PromptCompiler().compile(manifest)
    if compiled.get("executionManifestId") != manifest.get("manifestId"):
        raise ValueError("Compiled Prompt does not belong to the supplied Execution Manifest.")
    prompt_input = budgeted_prompt if isinstance(budgeted_prompt, dict) else compiled
    if budgeted_prompt is not None:
        if prompt_input.get("compiledPromptId") != compiled.get("compiledPromptId"):
            raise ValueError("Budgeted Prompt does not belong to the supplied Compiled Prompt.")
        if prompt_input.get("status") != "Ready":
            raise ValueError("Token Intelligence blocked this prompt because protected context exceeds the input budget.")

    sections = _adapter_sections(prompt_input)
    profile = budgetProfileForProvider(
        provider or "azure_phi",
        model or "",
        operation="build_dev_prompt",
        context_limit_override=context_limit_override,
    )
    budget_result = buildPrompt(sections, profile)
    optimized = budget_result.get("sections") if isinstance(budget_result.get("sections"), list) else sections
    final_prompt = format_developer_prompt(optimized, title="Execution Prompt")
    warnings = _warnings(compiled, budget_result)
    diagnostics = developer_prompt_diagnostics(
        budget_result=budget_result,
        warnings=warnings,
        section_count=len(optimized),
        package_id=str(manifest.get("sourcePackageId") or ""),
    )
    estimated_tokens = prompt_tokens(final_prompt)
    diagnostics.update(
        {
            "manifestId": manifest["manifestId"],
            "manifestVersion": manifest.get("manifestVersion"),
            "manifestHash": manifest.get("immutableHash"),
            "compiledPromptId": compiled.get("compiledPromptId"),
            "compilerVersion": compiled.get("compilerVersion"),
            "budgetedPromptId": prompt_input.get("budgetedPromptId"),
            "tokenIntelligence": prompt_input.get("diagnostics") if prompt_input.get("budgetedPromptId") else {},
            "sourcePackageId": manifest.get("sourcePackageId"),
            "contextRetrieved": False,
            "finalPromptMarkdownTokens": estimated_tokens,
        }
    )
    prompt_id = f"execprompt_{_stable_hash({'compiledPromptId': compiled.get('compiledPromptId'), 'budgetedPromptId': prompt_input.get('budgetedPromptId'), 'prompt': final_prompt})[:12]}"
    return {
        "executionPromptId": prompt_id,
        "promptId": prompt_id,
        "compiledPromptId": compiled.get("compiledPromptId"),
        "budgetedPromptId": prompt_input.get("budgetedPromptId"),
        "manifestId": manifest["manifestId"],
        "packageId": manifest.get("sourcePackageId"),
        "providerProfile": diagnostics.get("promptBudgetProfile") or profile.compression_strategy,
        "sections": [section.to_dict() for section in optimized],
        "finalPrompt": final_prompt,
        "prompt": final_prompt,
        "estimatedTokens": estimated_tokens,
        "warnings": warnings,
        "diagnostics": diagnostics,
        "generatedAt": now_iso(),
    }


def _adapter_sections(compiled: dict[str, Any]) -> list[PromptSection]:
    by_id = {section.get("id"): section for section in compiled.get("sections", []) if isinstance(section, dict)}
    repository = _content(by_id, "repository_context")
    implementation = _content(by_id, "implementation_guidance")
    validation = _content(by_id, "validation")
    qa = _content(by_id, "qa")
    constraints = _content(by_id, "constraints")
    business = _content(by_id, "business_objective")
    instructions = _content(by_id, "instructions")
    values = [
        _section("role", "Role", "You are a senior software engineer working inside the existing codebase.", 110, True, False, "instructions"),
        _section("objective", "Business Objective", business, 105, True, True, "instructions"),
        _section("repository_evidence", "Repository Context", _repository_adapter(repository), 90, True, True, "repository"),
        _section("planning_boundary", "Implementation Guidance", _implementation_adapter(implementation, constraints, repository), 100, True, True, "knowledge"),
        _section("validation", "Acceptance Criteria & Validation", _acceptance_adapter(validation.get("acceptanceCriteria", [])), 100, True, True, "validation"),
        _section("required_tests", "QA", _qa_tests(qa), 95, True, True, "validation"),
        _section("knowledge_summary", "Constraints", _constraint_lines(constraints), 85, True, True, "knowledge"),
        _section("instructions", "Instructions", instructions, 110, True, False, "instructions"),
        _section("output_schema", "Output Requirements", ["Summarize planned changes first.", "List files before editing.", "Implement minimal scoped changes and tests.", "Explain assumptions and validation results."], 110, True, False, "instructions"),
    ]
    return values


def _section(section_id: str, name: str, content: Any, priority: int, required: bool, compressible: bool, source: str) -> PromptSection:
    return PromptSection(section_id, name, priority, estimateTokens(json.dumps(content, sort_keys=True, default=str)), required, compressible, source, content)


def _content(by_id: dict[str, dict[str, Any]], section_id: str) -> dict[str, Any] | list[Any]:
    content = by_id.get(section_id, {}).get("content", {})
    return content if isinstance(content, (dict, list)) else {}


def _repository_adapter(repository: Any) -> dict[str, Any]:
    value = repository if isinstance(repository, dict) else {}
    return {
        "fileRankingStatus": "Repository file ranking available" if value.get("relevantFiles") else "Repository file ranking not available",
        "files": [_repository_item(item, "file") for item in value.get("relevantFiles", [])],
        "services": [_repository_item(item, "service") for item in value.get("relevantServices", [])],
        "apis": [_repository_item(item, "api") for item in value.get("relevantAPIs", [])],
        "modules": [_repository_item(item, "module") for item in value.get("relevantModules", [])],
        "flows": [_repository_item(item, "flow") for item in value.get("relevantFlows", [])],
    }


def _repository_item(value: Any, item_type: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "name": clean(value.get("name") or value.get("path") or value.get("title")),
            "type": clean(value.get("type")) or item_type,
            "confidence": value.get("confidence"),
            "reason": clean(value.get("reason")),
        }
    return {"name": clean(value), "type": item_type, "confidence": None, "reason": "Selected by Prompt Compiler."}


def _implementation_adapter(implementation: Any, constraints: Any, repository: Any) -> dict[str, Any]:
    guidance = implementation if isinstance(implementation, dict) else {}
    limits = constraints if isinstance(constraints, dict) else {}
    repo = repository if isinstance(repository, dict) else {}
    return {
        "inScope": guidance.get("implementationBoundaries") or guidance.get("inScope", []),
        "outOfScope": guidance.get("outOfScope", []),
        "allowedModules": _names(repo.get("relevantModules")),
        "blockedModules": _names(limits.get("blockedModules")),
        "allowedFlows": _names(repo.get("relevantFlows")),
        "blockedFlows": _names(limits.get("blockedFlows")),
        "constraints": _names(limits.get("architectureConstraints")),
        "assumptions": guidance.get("assumptions", []),
    }


def _qa_tests(qa: Any) -> list[dict[str, Any]]:
    value = qa if isinstance(qa, dict) else {}
    tests: list[dict[str, Any]] = []
    for field, test_type in (("suggestedTests", "functional"), ("regressionTests", "regression"), ("permissionTests", "permission"), ("negativeTests", "negative"), ("performanceTests", "performance")):
        for item in value.get(field, []) if isinstance(value.get(field), list) else []:
            tests.append(item if isinstance(item, dict) else {"type": test_type, "title": clean(item), "coverage": [], "priority": "Required"})
    return tests


def _acceptance_adapter(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            result.append({"id": "AC", "text": clean(item), "implementation": "", "validation": ""})
            continue
        result.append({
            "id": clean(item.get("acceptanceCriteriaId") or item.get("id")) or "AC",
            "text": clean(item.get("acceptanceText") or item.get("text")),
            "implementation": clean(item.get("implementationArea") or item.get("implementation")),
            "validation": clean(item.get("validationExpectation") or item.get("validation")),
        })
    return result


def _constraint_lines(constraints: Any) -> list[str]:
    value = constraints if isinstance(constraints, dict) else {}
    lines: list[str] = []
    for field in ("dependencies", "engineeringStandards", "blockedModules", "blockedFlows", "architectureConstraints", "permissionRequirements", "risks", "warnings"):
        for item in value.get(field, []) if isinstance(value.get(field), list) else []:
            text = clean(item.get("rule") or item.get("risk") or item.get("name") or item.get("title")) if isinstance(item, dict) else clean(item)
            if text and text not in lines:
                lines.append(text)
    return lines


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = clean(item.get("name") or item.get("title")) if isinstance(item, dict) else clean(item)
        if text:
            result.append(text)
    return result


def _warnings(compiled: dict[str, Any], budget_result: dict[str, Any]) -> list[str]:
    warnings = [clean(item) for item in compiled.get("warnings", []) if clean(item)]
    diagnostics = budget_result.get("diagnostics") if isinstance(budget_result.get("diagnostics"), dict) else {}
    if diagnostics.get("blockedByBudgetGuard"):
        warnings.append("Execution Prompt exceeded provider budget after compression.")
    if diagnostics.get("compressionApplied"):
        warnings.append("Execution Prompt sections were compressed for the selected provider budget.")
    return list(dict.fromkeys(warnings))


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
