"""Developer Prompt V2 builder.

Consumes only Execution Package V2 and produces a budget-safe, paste-ready
coding prompt. It does not query project profile, repository state, work item
text, or knowledge registry.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.prompt_budget import budgetProfileForProvider, buildPrompt

from .developer_prompt_diagnostics import developer_prompt_diagnostics
from .developer_prompt_model import clean, now_iso
from .prompt_output_formatter import format_developer_prompt, prompt_tokens
from .prompt_section_factory import developer_prompt_sections


def build_developer_prompt_v2(
    execution_package: dict[str, Any],
    *,
    provider: str = "azure_phi",
    model: str = "",
    context_limit_override: int | None = None,
) -> dict[str, Any]:
    package = execution_package if isinstance(execution_package, dict) else {}
    package_id = clean(package.get("packageId")) or f"execpkg_{_stable_hash(package)[:12]}"
    sections = developer_prompt_sections(package)
    profile = budgetProfileForProvider(
        provider or "azure_phi",
        model or "",
        operation="build_dev_prompt",
        context_limit_override=context_limit_override,
    )
    budget_result = buildPrompt(sections, profile)
    optimized_sections = budget_result.get("sections") if isinstance(budget_result.get("sections"), list) else sections
    final_prompt = format_developer_prompt(optimized_sections)
    warnings = _warnings(package, budget_result)
    diagnostics = developer_prompt_diagnostics(
        budget_result=budget_result,
        warnings=warnings,
        section_count=len(optimized_sections),
        package_id=package_id,
    )
    estimated_tokens = prompt_tokens(final_prompt)
    diagnostics["finalPromptMarkdownTokens"] = estimated_tokens
    return {
        "promptId": f"devprompt_{_stable_hash({'packageId': package_id, 'prompt': final_prompt})[:12]}",
        "packageId": package_id,
        "taskId": package.get("taskId"),
        "providerProfile": diagnostics.get("promptBudgetProfile") or profile.compression_strategy,
        "sections": [section.to_dict() for section in optimized_sections],
        "finalPrompt": final_prompt,
        "prompt": final_prompt,
        "estimatedTokens": estimated_tokens,
        "warnings": warnings,
        "diagnostics": diagnostics,
        "generatedAt": now_iso(),
    }


def _warnings(package: dict[str, Any], budget_result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    repository = package.get("repositoryContext") if isinstance(package.get("repositoryContext"), dict) else {}
    if not repository.get("relevantFiles"):
        warnings.append("Repository file ranking not available. Do not invent file paths.")
    readiness = package.get("readiness") if isinstance(package.get("readiness"), dict) else {}
    if readiness.get("status") in {"Needs Review", "NeedsReview", "Blocked"}:
        warnings.append(f"Execution readiness is {readiness.get('status')}. Review blockers before coding.")
    readiness_warnings = readiness.get("warnings") if isinstance(readiness.get("warnings"), list) else []
    for warning in readiness_warnings:
        text = clean(warning)
        if text and text not in warnings:
            warnings.append(text)
    diagnostics = budget_result.get("diagnostics") if isinstance(budget_result.get("diagnostics"), dict) else {}
    if diagnostics.get("blockedByBudgetGuard"):
        warnings.append("Prompt exceeded provider budget after compression. Review diagnostics before using.")
    if diagnostics.get("compressionApplied"):
        warnings.append("Prompt sections were compressed for the selected provider budget.")
    return warnings


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
