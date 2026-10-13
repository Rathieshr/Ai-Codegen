"""Deterministic, mode-aware optimization of immutable ExecutionPrompt artifacts."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.model_adapters.base import render_prompt_content
from backend.token_intelligence.models import estimate_tokens, stable_hash

from .modes import PromptModePolicy, resolve_mode
from .models import PROMPT_OPTIMIZER_VERSION, OptimizedExecutionPrompt, OptimizedPromptSection
from .scoring import score_prompt


PROTECTED_SECTION_IDS = frozenset({"repository_context", "implementation_guidance", "validation"})


class PromptOptimizer:
    version = PROMPT_OPTIMIZER_VERSION

    def optimize(self, execution_prompt: dict[str, Any], mode: str) -> OptimizedExecutionPrompt:
        source = deepcopy(execution_prompt) if isinstance(execution_prompt, dict) else {}
        self._validate(source)
        policy = resolve_mode(mode)
        sections, repetitions_removed, instruction_merges = _prepare_sections(source, policy)
        main, appendix = _place_sections(sections, policy)
        system_prompt = source.get("systemPrompt")
        objectives, objective_merges = _merge_similar_strings([
            str(source.get("adapterObjective") or ""),
            policy.objective,
        ])
        prompt = _render_prompt(main, appendix, objectives, mode=policy.mode, include_role=not bool(system_prompt))
        estimated = estimate_tokens({"systemPrompt": system_prompt or "", "prompt": prompt})
        max_input = int(source.get("maxInputTokens") or 0)
        all_sections = [*main, *appendix]
        quality, confidence, quality_breakdown, confidence_breakdown = score_prompt(all_sections, str(source.get("status") or ""))
        repository_mode = _repository_mode(all_sections)
        source_blocked = source.get("status") != "Ready"
        over_budget = estimated > max_input
        needs_review = repository_mode == "Unavailable" or quality < 70 or confidence < 0.65
        status = "Blocked" if source_blocked or over_budget else "NeedsReview" if needs_review else "Ready"
        warnings = list(dict.fromkeys([
            *[str(item) for item in source.get("warnings", []) if str(item)],
            *([] if repository_mode != "Unavailable" else ["Repository context is unavailable; prompt confidence is reduced."]),
            *([] if not over_budget else ["The optimized prompt exceeds the model input budget."]),
            *([] if quality >= 70 else ["Prompt Quality Score is below the review threshold."]),
            *([] if confidence >= 0.65 else ["Prompt Confidence is below the review threshold."]),
        ]))
        moved = [
            {"sectionId": section["id"], "reason": f"Lower priority for {policy.mode.replace('_', ' ')} mode."}
            for section in appendix
        ]
        core = {
            "optimizerVersion": self.version,
            "sourceExecutionPromptId": str(source.get("executionPromptId") or ""),
            "sourceBudgetedPromptId": str(source.get("sourceBudgetedPromptId") or ""),
            "sourceCompiledPromptId": str(source.get("sourceCompiledPromptId") or ""),
            "sourceExecutionManifestId": str(source.get("sourceExecutionManifestId") or ""),
            "modelId": str(source.get("modelId") or ""),
            "provider": str(source.get("provider") or ""),
            "mode": policy.mode,
            "systemPrompt": system_prompt,
            "prompt": prompt,
            "sections": main,
            "appendix": appendix,
            "estimatedTokens": estimated,
            "maxInputTokens": max_input,
            "promptQualityScore": quality,
            "promptConfidence": confidence,
            "status": status,
            "warnings": warnings,
        }
        immutable_hash = stable_hash(core)
        return {
            "optimizedPromptId": f"optimizedprompt_{immutable_hash[:12]}",
            **core,
            "immutable": True,
            "immutableHash": immutable_hash,
            "optimizedAt": datetime.now(timezone.utc).isoformat(),
            "diagnostics": {
                "optimizerVersion": self.version,
                "mode": policy.mode,
                "sourcePromptTokens": int(source.get("estimatedTokens") or 0),
                "optimizedPromptTokens": estimated,
                "tokenDelta": estimated - int(source.get("estimatedTokens") or 0),
                "repetitionsRemoved": repetitions_removed,
                "instructionsMerged": instruction_merges + objective_merges,
                "movedToAppendix": moved,
                "mainSectionOrder": [section["id"] for section in main],
                "appendixSectionOrder": [section["id"] for section in appendix],
                "qualityBreakdown": quality_breakdown,
                "confidenceBreakdown": confidence_breakdown,
                "acceptancePreserved": _section_content(source, "validation") == _section_content(all_sections, "validation"),
                "repositoryEvidencePreserved": _section_content(source, "repository_context") == _section_content(all_sections, "repository_context"),
                "implementationGuidancePreserved": _section_content(source, "implementation_guidance") == _section_content(all_sections, "implementation_guidance"),
                "sourceReady": not source_blocked,
                "contextLimitRespected": not over_budget,
                "sourceTokenIntelligence": deepcopy((source.get("diagnostics") or {}).get("sourceTokenIntelligence") or {}),
                "providerInvoked": False,
                "networkCalls": 0,
                "llmUsed": False,
            },
        }

    @staticmethod
    def _validate(source: dict[str, Any]) -> None:
        if not source.get("executionPromptId") or source.get("immutable") is not True:
            raise ValueError("An immutable ExecutionPrompt is required.")
        if not isinstance(source.get("sections"), list):
            raise ValueError("ExecutionPrompt sections are required.")


def optimize_execution_prompt(execution_prompt: dict[str, Any], mode: str) -> dict[str, Any]:
    return PromptOptimizer().optimize(execution_prompt, mode)


def _prepare_sections(
    source: dict[str, Any], policy: PromptModePolicy
) -> tuple[list[OptimizedPromptSection], int, int]:
    by_id = {
        str(section.get("id") or ""): deepcopy(section)
        for section in source.get("sections", [])
        if isinstance(section, dict) and section.get("id")
    }
    result: list[OptimizedPromptSection] = []
    repetitions_removed = 0
    instruction_merges = 0
    for section_id in policy.section_order:
        section = by_id.get(section_id)
        if not section:
            continue
        content = deepcopy(section.get("content"))
        if section_id == "instructions":
            raw = [
                *(_string_items(content)),
                *[str(item) for item in source.get("modelInstructions", [])],
                *policy.instructions,
            ]
            content, instruction_merges = _merge_similar_strings(raw)
        elif section_id not in PROTECTED_SECTION_IDS:
            content, removed = _dedupe_value(content)
            repetitions_removed += removed
        result.append({
            "id": section_id,
            "order": len(result) + 1,
            "title": str(section.get("title") or section_id.replace("_", " ").title()),
            "content": content,
            "rendered": render_prompt_content(content),
            "placement": "appendix" if section_id in policy.appendix_sections else "main",
        })
    return result, repetitions_removed, instruction_merges


def _place_sections(
    sections: list[OptimizedPromptSection], policy: PromptModePolicy
) -> tuple[list[OptimizedPromptSection], list[OptimizedPromptSection]]:
    main = [deepcopy(section) for section in sections if section["id"] not in policy.appendix_sections]
    appendix = [deepcopy(section) for section in sections if section["id"] in policy.appendix_sections]
    for index, section in enumerate(main, start=1):
        section["order"] = index
        section["placement"] = "main"
    for index, section in enumerate(appendix, start=1):
        section["order"] = index
        section["placement"] = "appendix"
    return main, appendix


def _render_prompt(
    main: list[OptimizedPromptSection],
    appendix: list[OptimizedPromptSection],
    objectives: list[str],
    *,
    mode: str,
    include_role: bool,
) -> str:
    blocks = ["# Optimized Execution Prompt"]
    if include_role:
        blocks.extend(["## Role", "You are a senior software engineer working inside the existing codebase."])
    blocks.extend(["## Execution Mode", mode.replace("_", " ").title(), "## Objective", *objectives])
    for section in main:
        if section["rendered"]:
            blocks.extend([f"## {section['title']}", section["rendered"]])
    if appendix:
        blocks.append("## Appendix")
        for section in appendix:
            if section["rendered"]:
                blocks.extend([f"### {section['title']}", section["rendered"]])
    return "\n\n".join(block for block in blocks if block).strip() + "\n"


def _dedupe_value(value: Any) -> tuple[Any, int]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        removed = 0
        for key, item in value.items():
            result[str(key)], count = _dedupe_value(item)
            removed += count
        return result, removed
    if isinstance(value, list):
        normalized_items: list[Any] = []
        removed = 0
        seen: set[str] = set()
        for item in value:
            normalized, count = _dedupe_value(item)
            removed += count
            key = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).casefold()
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            normalized_items.append(normalized)
        return normalized_items, removed
    return deepcopy(value), 0


def _merge_similar_strings(values: list[str]) -> tuple[list[str], int]:
    result: list[str] = []
    merged = 0
    for value in values:
        clean = " ".join(str(value or "").split()).strip()
        if not clean:
            continue
        match = next((index for index, existing in enumerate(result) if _similar(existing, clean)), None)
        if match is None:
            result.append(clean)
        else:
            if len(clean) > len(result[match]):
                result[match] = clean
            merged += 1
    return result, merged


def _similar(left: str, right: str) -> bool:
    left_normalized = _normalized_text(left)
    right_normalized = _normalized_text(right)
    if left_normalized == right_normalized:
        return True
    left_tokens = set(left_normalized.split())
    right_tokens = set(right_normalized.split())
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= 0.82


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _string_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if not isinstance(item, (dict, list))]
    if isinstance(value, str):
        return [value]
    return []


def _repository_mode(sections: list[dict[str, Any]]) -> str:
    content = _section_content(sections, "repository_context")
    return str(content.get("repositoryMode") or "Unavailable") if isinstance(content, dict) else "Unavailable"


def _section_content(source: dict[str, Any] | list[dict[str, Any]], section_id: str) -> Any:
    sections = source.get("sections", []) if isinstance(source, dict) else source
    for section in sections:
        if isinstance(section, dict) and section.get("id") == section_id:
            return deepcopy(section.get("content"))
    return None
