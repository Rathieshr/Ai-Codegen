"""Deterministic engineering skill matching."""

from __future__ import annotations

import re
from typing import Any

from .types import EngineeringSkill, SkillMatch


class SkillMatcher:
    def match(
        self,
        execution_package: dict[str, Any],
        skills: list[EngineeringSkill],
        memory_context: dict[str, Any] | None = None,
        max_results: int = 8,
    ) -> list[SkillMatch]:
        haystack_parts = _collect_text(execution_package)
        haystack_parts.extend(_collect_text(memory_context or {}))
        haystack = " ".join(haystack_parts).lower()
        artifact_type = _clean(execution_package.get("artifactType") or execution_package.get("packageType") or "Execution Package")
        matches: list[SkillMatch] = []
        for skill in skills:
            score = 0.0
            reasons: list[str] = []
            evidence: list[str] = []
            if artifact_type in skill.supported_artifacts or "Execution Package" in skill.supported_artifacts:
                score += 1.0
                reasons.append("artifact supported")
            for keyword in skill.match_keywords:
                normalized = keyword.lower()
                if normalized and normalized in haystack:
                    score += 1.25
                    reasons.append(f"matched keyword: {keyword}")
                    evidence.append(keyword)
            for hint in skill.repository_hints:
                normalized = hint.lower()
                if normalized and normalized in haystack:
                    score += 0.9
                    reasons.append(f"repository hint: {hint}")
                    evidence.append(hint)
            for context_name in skill.required_context:
                if _loose_contains(haystack, context_name):
                    score += 0.5
                    reasons.append(f"context available: {context_name}")
            if skill.category.lower() in haystack:
                score += 0.7
                reasons.append(f"category signal: {skill.category}")
            if score >= 1.5:
                confidence_boost = min(0.15, score / 50)
                skill.confidence = min(0.98, max(skill.confidence, 0.72 + confidence_boost))
                matches.append(SkillMatch(skill=skill, match_score=score, match_reasons=_dedupe(reasons), evidence=_dedupe(evidence)))
        matches.sort(key=lambda item: (item.match_score, item.skill.confidence, item.skill.usage_count), reverse=True)
        return matches[:max_results]


def _collect_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, int | float | bool):
        return [str(value)]
    if isinstance(value, list | tuple | set):
        parts: list[str] = []
        for item in value:
            parts.extend(_collect_text(item))
        return parts
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            if key in {"prompt", "finalPrompt", "devPrompt", "uiPrompt", "qaPrompt", "copilotContext"}:
                continue
            parts.append(str(key))
            parts.extend(_collect_text(item))
        return parts
    return [str(value)]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _loose_contains(haystack: str, needle: str) -> bool:
    terms = [term for term in re.split(r"[^a-zA-Z0-9]+", needle.lower()) if term]
    if not terms:
        return False
    return all(term in haystack for term in terms[:3])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
