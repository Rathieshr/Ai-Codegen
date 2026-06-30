"""Budget-safe provider invocation helpers."""

from __future__ import annotations

import inspect
import json
import os
from typing import Any

from .manager import budgetProfileForProvider, buildPrompt, estimateTokens
from .models import PromptSection


DEFAULT_SYSTEM_PROMPT = "Return strict JSON only."


def make_section(
    section_id: str,
    name: str,
    content: Any,
    *,
    priority: int = 50,
    required: bool = False,
    compressible: bool = True,
    source: str = "general",
) -> PromptSection:
    return PromptSection(
        id=section_id,
        name=name,
        priority=priority,
        estimatedTokens=estimateTokens(json.dumps(content, ensure_ascii=True, separators=(",", ":"), default=str)),
        required=required,
        compressible=compressible,
        source=source,
        content=content,
    )


def default_json_sections(
    *,
    role: str,
    objective: str,
    current_work_item: Any,
    instructions: str,
    output_schema: Any,
    dna: Any | None = None,
    capability: Any | None = None,
    planning_boundary: Any | None = None,
    repository_evidence: Any | None = None,
    knowledge_summary: Any | None = None,
    validation_summary: Any | None = None,
    previous_draft: Any | None = None,
    examples: Any | None = None,
    diagnostics: Any | None = None,
) -> list[PromptSection]:
    sections = [
        make_section("role", "Role", role, priority=100, required=True, compressible=False, source="role"),
        make_section("objective", "Objective", objective, priority=100, required=True, compressible=False, source="objective"),
        make_section("current_work_item", "Current Work Item", current_work_item, priority=100, required=True, compressible=False, source="work_item"),
        make_section("instructions", "Instructions", instructions, priority=100, required=True, compressible=False, source="instructions"),
        make_section("output_schema", "Output Schema", output_schema, priority=100, required=True, compressible=False, source="schema"),
    ]
    optional_specs = [
        ("dna", "DNA", dna, 95, "dna"),
        ("current_capability", "Capability", capability, 100, "capability"),
        ("planning_boundary", "Planning Boundary", planning_boundary, 90, "planning_boundary"),
        ("repository_evidence", "Repository Evidence", repository_evidence, 80, "repository"),
        ("knowledge_summary", "Knowledge Summary", knowledge_summary, 60, "knowledge"),
        ("validation", "Validation Summary", validation_summary, 85, "validation"),
        ("previous_draft_summary", "Previous Draft Summary", previous_draft, 50, "draft"),
        ("examples", "Examples", examples, 40, "examples"),
        ("diagnostics", "Diagnostics", diagnostics, 20, "diagnostics"),
    ]
    for section_id, name, content, priority, source in optional_specs:
        if content in (None, "", [], {}):
            continue
        sections.append(make_section(section_id, name, content, priority=priority, required=False, compressible=True, source=source))
    return sections


def probe_json_with_budget(
    provider: Any,
    sections: list[PromptSection],
    *,
    operation: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_tokens: int = 300,
    timeout_seconds: int | None = None,
    response_format_enabled: bool | None = False,
    allow_retry_without_response_format: bool = True,
    include_model_field: bool | None = None,
    api_version_override: str | None = None,
) -> dict[str, Any]:
    provider_name = _provider_name(provider)
    provider_model = _provider_model(provider)
    profile = budgetProfileForProvider(
        provider_name,
        provider_model,
        operation=operation,
        max_prompt_chars=_provider_prompt_char_limit(provider),
        context_limit_override=_provider_context_limit(provider),
    )
    result = buildPrompt(sections, profile)
    diagnostics = result["diagnostics"]
    if diagnostics.get("blocked") or diagnostics.get("estimated_tokens", 0) > diagnostics.get("model_context_limit", 0):
        return {
            "status": "blocked_by_budget_guard",
            "failure_reason": diagnostics.get("reason") or "prompt_budget_exceeded",
            "failure_message": diagnostics.get("recommendation") or "Prompt budget validation blocked provider execution.",
            "parsed_json": {},
            "raw_content": "",
            "http_status": None,
            "prompt_budget": diagnostics,
        }
    user_prompt = str(result["prompt"])
    try:
        probe = getattr(provider, "probe_json", None)
        if callable(probe):
            call_kwargs = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
                "response_format_enabled": response_format_enabled,
                "allow_retry_without_response_format": allow_retry_without_response_format,
                "include_model_field": include_model_field,
                "api_version_override": api_version_override,
            }
            response = _call_with_supported_kwargs(probe, call_kwargs)
        else:
            response = {
                "status": "success",
                "parsed_json": provider.refine_json(system_prompt, user_prompt, max_tokens=max_tokens),
                "raw_content": "",
                "http_status": 200,
            }
    except Exception as exc:
        return {
            "status": "provider_error",
            "failure_reason": type(exc).__name__,
            "failure_message": str(exc),
            "parsed_json": {},
            "raw_content": "",
            "http_status": None,
            "prompt_budget": diagnostics,
        }
    if not isinstance(response, dict):
        try:
            refined = provider.refine_json(system_prompt, user_prompt, max_tokens=max_tokens)
        except Exception:
            refined = {}
        response = {
            "status": "success" if isinstance(refined, dict) and refined else "unusable_response",
            "parsed_json": refined if isinstance(refined, dict) else {},
            "raw_content": "",
            "http_status": 200 if isinstance(refined, dict) and refined else None,
        }
    response["prompt_budget"] = diagnostics
    return response


def refine_json_with_budget(
    provider: Any,
    sections: list[PromptSection],
    *,
    operation: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_tokens: int = 300,
) -> dict[str, Any]:
    provider_name = _provider_name(provider)
    provider_model = _provider_model(provider)
    profile = budgetProfileForProvider(
        provider_name,
        provider_model,
        operation=operation,
        max_prompt_chars=_provider_prompt_char_limit(provider),
        context_limit_override=_provider_context_limit(provider),
    )
    result = buildPrompt(sections, profile)
    diagnostics = result["diagnostics"]
    if diagnostics.get("blocked") or diagnostics.get("estimated_tokens", 0) > diagnostics.get("model_context_limit", 0):
        return {}
    try:
        raw = provider.refine_json(system_prompt, str(result["prompt"]), max_tokens=max_tokens)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _call_with_supported_kwargs(func: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        signature = None
    filtered = {key: value for key, value in kwargs.items() if value is not None}
    if signature is not None and not any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        filtered = {key: value for key, value in filtered.items() if key in signature.parameters}
    return func(**filtered)


def _provider_name(provider: Any) -> str:
    config = provider.safe_config() if hasattr(provider, "safe_config") else {}
    return str(config.get("provider") or os.getenv("AI_GEN_REFINER_PROVIDER") or "azure_phi")


def _provider_model(provider: Any) -> str:
    config = provider.safe_config() if hasattr(provider, "safe_config") else {}
    health = provider.health_snapshot() if hasattr(provider, "health_snapshot") else {}
    return str(config.get("deployment") or health.get("deployment") or config.get("model") or os.getenv("AI_GEN_REFINER_DEPLOYMENT") or os.getenv("AI_GEN_REFINER_MODEL") or "")


def _provider_prompt_char_limit(provider: Any) -> int:
    config = provider.safe_config() if hasattr(provider, "safe_config") else {}
    try:
        return int(config.get("max_prompt_chars") or os.getenv("AI_GEN_REFINER_MAX_PROMPT_CHARS") or "4800")
    except (TypeError, ValueError):
        return 4800


def _provider_context_limit(provider: Any) -> int:
    try:
        configured = int(os.getenv("AI_GEN_PROJECT_MODEL_CONTEXT_TOKENS", "0") or "0")
    except ValueError:
        configured = 0
    char_limit = max(1, _provider_prompt_char_limit(provider) // 4)
    return min(configured, char_limit) if configured else char_limit
