"""Deterministic Token Budget Engine for immutable CompiledPrompt artifacts.

The engine removes complete low-value JSON values. It never truncates strings,
serialised JSON, acceptance criteria, repository evidence, or validation
guidance. If protected context cannot fit, the result is blocked and retains
that protected context intact.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .models import (
    DEFAULT_OUTPUT_RESERVES,
    SUPPORTED_TOKEN_BUDGETS,
    TOKEN_INTELLIGENCE_VERSION,
    BudgetedPrompt,
    RemovedContext,
    estimate_tokens,
    now_iso,
    stable_hash,
)


PROTECTED_SECTION_IDS = frozenset({"repository_context", "validation"})


class ITokenBudgetEngine(Protocol):
    def optimize(
        self,
        compiled_prompt: dict[str, Any],
        *,
        budget_tokens: int,
        reserved_output_tokens: int | None = None,
        actual_tokens: int | None = None,
    ) -> BudgetedPrompt: ...


@dataclass(frozen=True, slots=True)
class _Candidate:
    priority: int
    section_order: int
    path: tuple[Any, ...]
    section_id: str
    reason: str


class TokenBudgetEngine:
    version = TOKEN_INTELLIGENCE_VERSION

    def optimize(
        self,
        compiled_prompt: dict[str, Any],
        *,
        budget_tokens: int,
        reserved_output_tokens: int | None = None,
        actual_tokens: int | None = None,
    ) -> BudgetedPrompt:
        compiled = deepcopy(compiled_prompt) if isinstance(compiled_prompt, dict) else {}
        self._validate(compiled, budget_tokens, reserved_output_tokens, actual_tokens)
        reserve = int(reserved_output_tokens if reserved_output_tokens is not None else DEFAULT_OUTPUT_RESERVES[budget_tokens])
        input_budget = budget_tokens - reserve
        sections = deepcopy(compiled.get("sections") or [])
        before_sections = deepcopy(sections)
        estimated_before = _sections_tokens(sections)
        removed: list[RemovedContext] = []

        for candidate in _removal_candidates(sections):
            if _sections_tokens(sections) <= input_budget:
                break
            value = _remove_path(sections, candidate.path)
            if value is _MISSING:
                continue
            removed.append(_removed_context(candidate, value))

        estimated_after = _sections_tokens(sections)
        protected_before = _protected_values(before_sections)
        protected_after = _protected_values(sections)
        protected_preserved = protected_before == protected_after
        json_integrity = _json_round_trip(sections)
        fits = estimated_after <= input_budget
        core = {
            "tokenIntelligenceVersion": self.version,
            "compiledPromptId": str(compiled.get("compiledPromptId") or ""),
            "executionManifestId": str(compiled.get("executionManifestId") or ""),
            "requestedBudgetTokens": budget_tokens,
            "reservedOutputTokens": reserve,
            "inputBudgetTokens": input_budget,
            "sections": sections,
            "status": "Ready" if fits else "Blocked",
        }
        immutable_hash = stable_hash(core)
        section_tokens_before = _section_tokens(before_sections)
        section_tokens_after = _section_tokens(sections)
        section_allocation = {
            section_id: {
                "allocatedTokens": tokens,
                "protected": section_id in PROTECTED_SECTION_IDS,
                "inputBudgetSharePercent": round((tokens / input_budget) * 100, 2) if input_budget else 0,
            }
            for section_id, tokens in section_tokens_after.items()
        }
        return {
            "budgetedPromptId": f"budgetedprompt_{immutable_hash[:12]}",
            **core,
            "immutable": True,
            "immutableHash": immutable_hash,
            "optimizedAt": now_iso(),
            "diagnostics": {
                "supportedBudgets": list(SUPPORTED_TOKEN_BUDGETS),
                "estimatedTokensBefore": estimated_before,
                "estimatedTokens": estimated_after,
                "actualTokens": int(actual_tokens) if actual_tokens is not None else None,
                "actualTokensSource": "provider_usage" if actual_tokens is not None else "not_available",
                "removedContext": removed,
                "removedContextCount": len(removed),
                "remainingBudget": input_budget - estimated_after,
                "overflowTokens": max(0, estimated_after - input_budget),
                "sectionTokensBefore": section_tokens_before,
                "sectionTokensAfter": section_tokens_after,
                "sectionBudgetAllocation": section_allocation,
                "acceptanceCriteriaPreserved": protected_before["acceptanceCriteria"] == protected_after["acceptanceCriteria"],
                "repositoryEvidencePreserved": protected_before["repositoryContext"] == protected_after["repositoryContext"],
                "validationGuidancePreserved": protected_before["validationGuidance"] == protected_after["validationGuidance"],
                "protectedContextPreserved": protected_preserved,
                "jsonIntegrityValid": json_integrity,
                "trimStrategy": "whole_json_value_removal",
                "jsonTruncated": False,
                "blockedByBudgetGuard": not fits,
                "blockReason": "protected_context_exceeds_input_budget" if not fits else "",
                "tokenOptimizationApplied": bool(removed),
                "modelAdaptationApplied": False,
                "providerSelected": False,
                "llmUsed": False,
            },
        }

    @staticmethod
    def _validate(compiled: dict[str, Any], budget_tokens: int, reserved_output_tokens: int | None, actual_tokens: int | None) -> None:
        if not compiled.get("compiledPromptId") or compiled.get("immutable") is not True:
            raise ValueError("An immutable CompiledPrompt is required.")
        if budget_tokens not in SUPPORTED_TOKEN_BUDGETS:
            supported = ", ".join(str(value) for value in SUPPORTED_TOKEN_BUDGETS)
            raise ValueError(f"Unsupported token budget. Supported budgets: {supported}.")
        reserve = reserved_output_tokens if reserved_output_tokens is not None else DEFAULT_OUTPUT_RESERVES[budget_tokens]
        if not isinstance(reserve, int) or reserve < 0 or reserve >= budget_tokens:
            raise ValueError("reservedOutputTokens must be a non-negative integer smaller than budgetTokens.")
        if actual_tokens is not None and (not isinstance(actual_tokens, int) or actual_tokens < 0):
            raise ValueError("actualTokens must be a non-negative integer when provided.")


def _removal_candidates(sections: list[dict[str, Any]]) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        if section_id in PROTECTED_SECTION_IDS:
            continue
        content = section.get("content")
        candidates.extend(_content_candidates(content, (section_index, "content"), section_id, int(section.get("order") or section_index + 1)))
    return sorted(candidates, key=lambda item: (item.priority, item.section_order, _path_sort_key(item.path)))


def _content_candidates(content: Any, path: tuple[Any, ...], section_id: str, section_order: int) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    if isinstance(content, dict):
        for key in sorted(content):
            value = content[key]
            priority = _priority(section_id, str(key))
            if isinstance(value, list):
                for index in range(len(value) - 1, -1, -1):
                    candidates.append(_Candidate(priority, section_order, (*path, key, index), section_id, _reason(section_id, str(key))))
            elif isinstance(value, dict):
                candidates.extend(_content_candidates(value, (*path, key), section_id, section_order))
            else:
                candidates.append(_Candidate(priority, section_order, (*path, key), section_id, _reason(section_id, str(key))))
    elif isinstance(content, list):
        for index in range(len(content) - 1, -1, -1):
            candidates.append(_Candidate(_priority(section_id, "items"), section_order, (*path, index), section_id, _reason(section_id, "items")))
    return candidates


def _priority(section_id: str, field: str) -> int:
    key = field.casefold()
    if section_id == "business_objective" and key == "confidence":
        return 5
    if section_id == "qa":
        return 10
    if section_id == "constraints" and key in {"warnings", "risks"}:
        return 15
    if section_id == "implementation_guidance" and key in {"assumptions", "notes", "examples"}:
        return 20
    if section_id == "constraints":
        return 30
    if section_id == "implementation_guidance":
        return 40
    if section_id == "instructions":
        return 80
    if section_id == "business_objective":
        return 90
    return 50


def _reason(section_id: str, field: str) -> str:
    return f"Removed lower-value {section_id}.{field} context to satisfy the requested input budget."


def _remove_path(root: list[dict[str, Any]], path: tuple[Any, ...]) -> Any:
    current: Any = root
    try:
        for part in path[:-1]:
            current = current[part]
        final = path[-1]
        if isinstance(current, list) and isinstance(final, int):
            if final >= len(current):
                return _MISSING
            return current.pop(final)
        if isinstance(current, dict) and final in current:
            return current.pop(final)
    except (IndexError, KeyError, TypeError):
        return _MISSING
    return _MISSING


def _removed_context(candidate: _Candidate, value: Any) -> RemovedContext:
    preview = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return {
        "sectionId": candidate.section_id,
        "path": _path_text(candidate.path),
        "estimatedTokens": estimate_tokens(value),
        "reason": candidate.reason,
        "valueHash": stable_hash(value),
        "valuePreview": preview[:157] + "..." if len(preview) > 160 else preview,
    }


def _protected_values(sections: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(section.get("id") or ""): section for section in sections if isinstance(section, dict)}
    validation = by_id.get("validation", {}).get("content")
    validation = validation if isinstance(validation, dict) else {}
    return {
        "acceptanceCriteria": deepcopy(validation.get("acceptanceCriteria", [])),
        "validationGuidance": deepcopy(validation.get("guidance", {})),
        "repositoryContext": deepcopy(by_id.get("repository_context", {}).get("content", {})),
    }


def _sections_tokens(sections: list[dict[str, Any]]) -> int:
    return estimate_tokens({"sections": sections})


def _section_tokens(sections: list[dict[str, Any]]) -> dict[str, int]:
    return {
        str(section.get("id") or f"section_{index}"): estimate_tokens(section)
        for index, section in enumerate(sections)
        if isinstance(section, dict)
    }


def _json_round_trip(value: Any) -> bool:
    try:
        return json.loads(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)) == value
    except (TypeError, ValueError):
        return False


def _path_text(path: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for part in path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        elif parts:
            parts.append(f".{part}")
        else:
            parts.append(str(part))
    return "".join(parts)


def _path_sort_key(path: tuple[Any, ...]) -> tuple[Any, ...]:
    """Sort list indexes descending so removals cannot shift pending paths."""

    return tuple((0, str(part)) if not isinstance(part, int) else (1, -part) for part in path)


_MISSING = object()
