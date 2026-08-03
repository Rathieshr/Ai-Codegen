"""Provider-aware prompt budget management.

The manager works with ranked sections rather than a single concatenated prompt.
It compresses lower-priority context before provider execution and reports exactly
what changed.
"""

from __future__ import annotations

import copy
import json
import os
import time
from collections import OrderedDict
from typing import Any

from .models import PromptBudgetProfile, PromptSection, ProviderCapabilities


PROMPT_ORDER = [
    "role",
    "objective",
    "current_work_item",
    "current_intent",
    "current_capability",
    "dna",
    "planning_boundary",
    "validation",
    "repository_evidence",
    "knowledge_summary",
    "instructions",
    "output_schema",
]

SECTION_PRIORITIES = {
    "current_capability": 100,
    "epic_dna": 95,
    "dna": 95,
    "planning_boundary": 90,
    "validation": 85,
    "repository_evidence": 80,
    "relevant_modules": 75,
    "relevant_files": 70,
    "engineering_standards": 65,
    "knowledge_summary": 60,
    "previous_draft_summary": 50,
    "examples": 40,
    "diagnostics": 20,
    "current_intent": 100,
    "instructions": 100,
}


def estimateTokens(text: str) -> int:
    """Estimate prompt tokens using the existing HEI heuristic."""

    return max(1, (len(str(text)) + 3) // 4)


def providerCapabilities(
    provider: str = "azure_phi",
    model: str = "",
    *,
    max_prompt_chars: int | None = None,
    context_limit_override: int | None = None,
) -> ProviderCapabilities:
    """Resolve provider capabilities before selecting a budget profile."""

    provider_key = (provider or "azure_phi").strip().lower()
    context_limits = {
        "azure_phi": 1200,
        "phi": 1200,
        "gpt-5": 32000,
        "openai": 32000,
        "claude": 200000,
        "anthropic": 200000,
        "ollama": 8000,
    }
    resolved_limit = int(context_limit_override or context_limits.get(provider_key, 8000))
    resolved_chars = int(max_prompt_chars or max(1, resolved_limit * 4))
    if provider_key in {"azure_phi", "phi"} and max_prompt_chars:
        resolved_limit = min(resolved_limit, max(1, resolved_chars // 4))
    return ProviderCapabilities(
        provider=provider_key,
        model=model or "",
        context_limit=resolved_limit,
        max_output_tokens=_env_int("AI_GEN_REFINER_MAX_TOKENS", 300),
        supports_json_mode=provider_key not in {"azure_phi", "phi", "ollama"},
        max_prompt_chars=resolved_chars,
        safety_margin=180 if provider_key in {"azure_phi", "phi"} else 512,
    )


def budgetProfileForProvider(
    provider: str = "azure_phi",
    model: str = "",
    *,
    operation: str = "",
    max_prompt_chars: int | None = None,
    context_limit_override: int | None = None,
) -> PromptBudgetProfile:
    """Build the provider-specific budget profile used by the manager."""

    capabilities = providerCapabilities(
        provider,
        model,
        max_prompt_chars=max_prompt_chars,
        context_limit_override=context_limit_override,
    )
    if capabilities.provider in {"azure_phi", "phi"}:
        if operation.startswith("build_"):
            section_budgets = {
                "current_work_item": 80,
                "current_intent": 80,
                "current_capability": 120,
                "dna": 160,
                "planning_boundary": 120,
                "validation": 100,
                "evidence_catalog": 100,
                "repository_evidence": 140,
                "knowledge_summary": 110,
                "instructions": 140,
                "draft": 120,
                "previous_draft_summary": 120,
            }
        else:
            section_budgets = {
                "current_work_item": 100,
                "current_intent": 100,
                "current_capability": 120,
                "dna": 180,
                "planning_boundary": 140,
                "validation": 120,
                "evidence_catalog": 120,
                "repository_evidence": 180,
                "knowledge_summary": 120,
                "instructions": 150,
                "draft": 120,
                "previous_draft_summary": 120,
            }
        reserved = 180
        reserved_output = 250
        strategy = "aggressive"
    elif capabilities.context_limit >= 100000:
        section_budgets = {}
        reserved = 2048
        reserved_output = 8000
        strategy = "minimal"
    elif capabilities.context_limit >= 32000:
        section_budgets = {}
        reserved = 1024
        reserved_output = 4000
        strategy = "balanced"
    else:
        section_budgets = {"draft": 600, "repository_evidence": 1200, "knowledge_summary": 1000}
        reserved = 512
        reserved_output = 1000
        strategy = "balanced"
    input_budget = max(1, capabilities.context_limit - reserved_output)
    return PromptBudgetProfile(
        provider=capabilities.provider,
        model=model or capabilities.model,
        context_limit=capabilities.context_limit,
        reserved_tokens=reserved,
        reserved_output_tokens=reserved_output,
        input_budget=input_budget,
        compression_strategy=strategy,
        section_budgets=section_budgets,
        compression_order=["draft", "knowledge", "repository", "engineering_context"],
        removable_sources=["examples", "diagnostics"],
        capabilities=capabilities,
    )


def buildPrompt(sections: list[PromptSection], profile: PromptBudgetProfile) -> dict[str, Any]:
    """Compress, validate, and assemble a provider-ready prompt."""

    started = time.monotonic()
    optimized, compression_diagnostics = compressSections(sections, profile)
    validation = validateBudget(optimized, profile)
    prompt = assemblePrompt(optimized)
    required_validation = validateBudget([section for section in optimized if section.required], profile)
    blocked_by_required = required_validation["estimated_tokens"] > profile.context_limit
    diagnostics = {
        **validation,
        **compression_diagnostics,
        "provider": profile.provider,
        "model": profile.model,
        "budget_profile": profile.to_dict(),
        "budget_profile_name": _profile_name(profile),
        "provider_capabilities": profile.capabilities.to_dict() if profile.capabilities else {},
        "contextLimit": profile.context_limit,
        "reservedOutputTokens": profile.reserved_output_tokens,
        "inputBudget": profile.input_budget,
        "finalPromptTokens": validation["estimated_tokens"],
        "compressionApplied": bool(compression_diagnostics.get("compression_applied")),
        "removedSections": compression_diagnostics.get("removed_sections", []),
        "largestSection": validation.get("largest_section", {}),
        "blockedByBudgetGuard": bool(blocked_by_required or not validation["fits"]),
        "prompt_size": len(prompt),
        "budget_used": validation["estimated_tokens"],
        "prompt_sections": [section.to_dict() for section in optimized],
        "prompt_section_order": [section.id for section in optimized],
        "execution_time_ms": int((time.monotonic() - started) * 1000),
    }
    if blocked_by_required:
        diagnostics.update(
            {
                "blocked": True,
                "reason": "required_sections_exceed_budget",
                "requiredTokens": required_validation["estimated_tokens"],
                "modelLimit": profile.context_limit,
                "largestRequiredSection": required_validation["largest_section"].get("section", ""),
                "recommendation": "Reduce required work item, DNA, instruction, or output schema text before calling the provider.",
            }
        )
    return {"prompt": prompt, "sections": optimized, "diagnostics": diagnostics}


def compressSections(sections: list[PromptSection], profile: PromptBudgetProfile) -> tuple[list[PromptSection], dict[str, Any]]:
    """Apply deterministic compression and optional-section removal."""

    working = [_refresh_tokens(_clone_section(section)) for section in sections]
    compression_steps: list[dict[str, Any]] = []
    removed_sections: list[str] = []
    if profile.context_limit <= 2000:
        retained = []
        for section in working:
            if section.source in {"examples", "diagnostics"} and not section.required:
                removed_sections.append(section.id)
                compression_steps.append({"action": "remove_small_model_optional", "section": section.id, "source": section.source})
            else:
                retained.append(section)
        working = retained
    for source in profile.compression_order:
        working, steps = _compress_source(working, profile, source)
        compression_steps.extend(steps)
        if validateBudget(working, profile)["fits"]:
            break
    if not validateBudget(working, profile)["fits"]:
        for source in profile.removable_sources:
            kept = []
            for section in working:
                if section.source == source and not section.required:
                    removed_sections.append(section.id)
                    compression_steps.append({"action": "remove", "section": section.id, "source": source})
                else:
                    kept.append(section)
            working = kept
            if validateBudget(working, profile)["fits"]:
                break
    if not validateBudget(working, profile)["fits"]:
        for section in sorted(list(working), key=lambda item: (item.required, item.priority, item.id)):
            if section.required:
                continue
            working.remove(section)
            removed_sections.append(section.id)
            compression_steps.append({"action": "remove_low_priority", "section": section.id, "priority": section.priority})
            if validateBudget(working, profile)["fits"]:
                break
    return _sort_sections(working), {
        "compression_steps": compression_steps,
        "removed_sections": _unique(removed_sections),
        "compression_applied": bool(compression_steps),
    }


def validateBudget(sections: list[PromptSection], profile: PromptBudgetProfile) -> dict[str, Any]:
    section_tokens = {section.id: _section_tokens(section) for section in sections}
    total = sum(section_tokens.values()) + int(profile.reserved_tokens)
    largest_id = max(section_tokens, key=section_tokens.get) if section_tokens else ""
    largest = {"section": largest_id, "tokens": section_tokens.get(largest_id, 0)}
    limit = int(profile.context_limit)
    return {
        "estimated_tokens": total,
        "model_context_limit": limit,
        "remaining_budget": limit - total,
        "overflow_tokens": max(0, total - limit),
        "largest_section": largest,
        "fits": total <= limit,
        "section_tokens": section_tokens,
    }


def assemblePrompt(sections: list[PromptSection]) -> str:
    ordered = OrderedDict()
    for section in _sort_sections(sections):
        ordered[section.id] = section.content
    return json.dumps(ordered, ensure_ascii=True, separators=(",", ":"))


def summarizeDraft(content: Any, max_tokens: int = 120) -> Any:
    """Compact previous drafts without carrying whole generated prompts forward."""

    data = _coerce_mapping(content)
    if not data:
        return _truncate_by_tokens(_clean_text(content), max_tokens)
    important_keys = [
        "target_output",
        "work_item_type",
        "business_goal",
        "businessValue",
        "business_value",
        "capability",
        "title",
        "user_story",
        "affected_modules",
        "affected_flows",
        "dependencies",
        "description",
        "validation_issues",
        "missing_items",
        "user_edits",
        "acceptance_criteria",
        "tasks",
    ]
    summary: dict[str, Any] = {}
    for key in important_keys:
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if key in {"description", "business_goal", "businessValue", "business_value"}:
            summary[key] = _truncate_by_tokens(_clean_text(value), 45)
        elif isinstance(value, list):
            summary[key] = [_truncate_by_tokens(_clean_text(item), 24) for item in value[:4]]
        else:
            summary[key] = _truncate_by_tokens(_clean_text(value), 30)
    if not summary:
        summary = {"summary": _truncate_by_tokens(json.dumps(data, ensure_ascii=True, default=str), max_tokens)}
    while estimateTokens(json.dumps(summary, ensure_ascii=True, separators=(",", ":"))) > max_tokens and len(summary) > 1:
        summary.pop(next(reversed(summary)))
    return summary


def _compress_source(
    sections: list[PromptSection], profile: PromptBudgetProfile, source: str
) -> tuple[list[PromptSection], list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    compressed = []
    for section in sections:
        updated = _clone_section(section)
        if not section.compressible or section.source != source:
            compressed.append(updated)
            continue
        before = _section_tokens(updated)
        budget = _section_budget(updated, profile)
        if before <= budget:
            compressed.append(updated)
            continue
        if source == "draft":
            updated.content = summarizeDraft(updated.content, budget)
        elif source == "knowledge":
            updated.content = _compress_knowledge(updated.content, budget)
        elif source == "repository":
            updated.content = _compress_repository(updated.content, budget)
        else:
            updated.content = _truncate_by_tokens(updated.content, budget)
        updated = _refresh_tokens(updated)
        after = _section_tokens(updated)
        steps.append(
            {
                "action": "compress",
                "section": updated.id,
                "source": source,
                "before_tokens": before,
                "after_tokens": after,
                "budget_tokens": budget,
            }
        )
        compressed.append(updated)
    return compressed, steps


def _section_budget(section: PromptSection, profile: PromptBudgetProfile) -> int:
    if section.id in profile.section_budgets:
        return max(1, int(profile.section_budgets[section.id]))
    if section.source in profile.section_budgets:
        return max(1, int(profile.section_budgets[section.source]))
    return max(40, int(profile.context_limit * 0.2))


def _compress_knowledge(content: Any, budget: int) -> Any:
    data = _coerce_mapping(content)
    if not data:
        return _truncate_by_tokens(content, budget)
    compact = {
        "standards": _string_list(data.get("standards"))[:5],
        "architecture_summary": _truncate_by_tokens(data.get("architecture_summary"), max(20, budget // 5)),
        "modules": _string_list(data.get("modules"))[:6],
        "flows": _string_list(data.get("flows"))[:6],
    }
    compact = {key: value for key, value in compact.items() if value not in ("", [], {}, None)}
    return _fit_mapping_to_budget(compact, budget)


def _compress_repository(content: Any, budget: int) -> Any:
    data = _coerce_mapping(content)
    if not data:
        return _truncate_by_tokens(content, budget)
    compact = {
        "files": _string_list(data.get("files") or data.get("relevant_files"))[:5],
        "modules": _string_list(data.get("modules"))[:5],
        "apis": _string_list(data.get("apis"))[:4],
        "services": _string_list(data.get("services"))[:4],
        "confidence": data.get("confidence"),
        "evidence": _string_list(data.get("evidence"))[:4],
    }
    compact = {key: value for key, value in compact.items() if value not in ("", [], {}, None)}
    return _fit_mapping_to_budget(compact, budget)


def _fit_mapping_to_budget(data: dict[str, Any], budget: int) -> dict[str, Any]:
    compact = copy.deepcopy(data)
    while estimateTokens(json.dumps(compact, ensure_ascii=True, separators=(",", ":"))) > budget and compact:
        key = next(reversed(compact))
        value = compact.get(key)
        if isinstance(value, list) and len(value) > 1:
            compact[key] = value[:-1]
        elif isinstance(value, str) and len(value) > 80:
            compact[key] = _truncate_by_tokens(value, max(10, budget // 4))
        else:
            compact.pop(key, None)
    return compact


def _sort_sections(sections: list[PromptSection]) -> list[PromptSection]:
    order = {section_id: index for index, section_id in enumerate(PROMPT_ORDER)}
    return sorted(sections, key=lambda section: (order.get(section.id, 100), -section.priority, section.id))


def _clone_section(section: PromptSection) -> PromptSection:
    return PromptSection(
        id=section.id,
        name=section.name,
        priority=section.priority,
        estimatedTokens=section.estimatedTokens,
        required=section.required,
        compressible=section.compressible,
        source=section.source,
        content=copy.deepcopy(section.content),
    )


def _refresh_tokens(section: PromptSection) -> PromptSection:
    section.estimatedTokens = _section_tokens(section)
    return section


def _section_tokens(section: PromptSection) -> int:
    return estimateTokens(json.dumps(section.content, ensure_ascii=True, separators=(",", ":"), default=str))


def _coerce_mapping(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _truncate_by_tokens(value: Any, max_tokens: int) -> str:
    text = _clean_text(value)
    max_chars = max(1, int(max_tokens) * 4)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.replace("\r", " ").split())
    return " ".join(json.dumps(value, ensure_ascii=True, default=str).split())


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    return []


def _unique(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _profile_name(profile: PromptBudgetProfile) -> str:
    return f"{profile.provider}:{profile.model or 'default'}:{profile.context_limit}"
