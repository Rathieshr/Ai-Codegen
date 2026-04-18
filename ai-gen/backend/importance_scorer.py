"""Simple deterministic importance scoring for business logic steps."""

from __future__ import annotations

import re
from typing import Any


KEYWORD_SCORES = {
    "payment": 0.95,
    "transaction": 0.95,
    "auth": 0.9,
    "login": 0.9,
    "password": 0.9,
    "token": 0.9,
    "validation": 0.8,
    "verify": 0.8,
    "database": 0.7,
    "data": 0.7,
    "api": 0.6,
    "logging": 0.3,
    "analytics": 0.3,
    "ui": 0.2,
}

ACTION_ADJUSTMENTS = {
    "generate": 0.1,
    "create": 0.1,
    "verify": 0.15,
    "validate": 0.15,
    "authenticate": 0.15,
    "check": 0.05,
    "log": -0.2,
    "track": -0.2,
    "record": -0.2,
}

DEFAULT_IMPORTANCE = 0.5
CRITICAL_THRESHOLD = 0.85


def score_step(step: str, intent: str = "general") -> dict[str, Any]:
    """Score one flow step from 0.0 to 1.0 using keywords and action signals."""

    tokens = re.findall(r"[a-z0-9]+", step.lower())
    matched_keywords = [
        keyword for keyword in KEYWORD_SCORES if _matches_keyword(tokens, keyword)
    ]
    raw_keyword_score = _keyword_score(matched_keywords)
    action_adjustment = _action_adjustment(tokens)

    # Action scoring starts from the keyword/default score so verbs like
    # "generate" can boost important objects such as tokens or payments.
    adjusted_action_score = _clamp(raw_keyword_score + action_adjustment)

    # Observability actions usually describe side effects, not core business
    # decisions, so their keyword contribution is dampened before combining.
    if action_adjustment < 0:
        keyword_score = adjusted_action_score
    else:
        keyword_score = raw_keyword_score

    intent_adjustment = _intent_adjustment(tokens, intent)
    importance = max(keyword_score, adjusted_action_score) + intent_adjustment

    return {
        "step": step,
        "importance": _clamp(importance),
        "matched_keywords": matched_keywords,
    }


def _keyword_score(matched_keywords: list[str]) -> float:
    """Return the strongest keyword score, falling back to the default."""

    return max(
        [KEYWORD_SCORES[keyword] for keyword in matched_keywords],
        default=DEFAULT_IMPORTANCE,
    )


def _action_adjustment(tokens: list[str]) -> float:
    """Return the adjustment for the leading action word, if present."""

    if not tokens:
        return 0.0
    return ACTION_ADJUSTMENTS.get(tokens[0], 0.0)


def _intent_adjustment(tokens: list[str], intent: str) -> float:
    """Adjust importance based on the detected user intent."""

    if intent == "bug_fix" and _has_bug_fix_signal(tokens):
        return 0.1
    if intent == "refactor" and _has_refactor_signal(tokens):
        return 0.1
    return 0.0


def _has_bug_fix_signal(tokens: list[str]) -> bool:
    """Bug fixes care more about validation, verification, and errors."""

    token_set = set(tokens)
    return (
        any(token.startswith("validat") for token in tokens)
        or any(token.startswith("verify") for token in tokens)
        or "error" in token_set
    )


def _has_refactor_signal(tokens: list[str]) -> bool:
    """Refactors care more about structure and dependency boundaries."""

    token_set = set(tokens)
    return bool(
        token_set.intersection(
            {"structure", "dependency", "dependencies", "service", "services", "database", "data", "api"}
        )
    )


def _clamp(score: float) -> float:
    """Keep scores inside the public 0.0 to 1.0 range."""

    return round(max(0.0, min(1.0, score)), 4)


def _matches_keyword(tokens: list[str], keyword: str) -> bool:
    """Match keywords against real tokens to avoid accidental substrings."""

    if keyword == "validation":
        return any(token.startswith("validat") for token in tokens)
    if keyword in {"auth", "login", "verify"}:
        return any(token.startswith(keyword) for token in tokens)
    return keyword in tokens


def score_flow(flow_steps: list[str], intent: str = "general") -> list[dict[str, Any]]:
    """Score all flow steps in their original order."""

    return [score_step(step, intent=intent) for step in flow_steps]


def sort_by_importance(scored_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return steps sorted by importance, highest first."""

    return sorted(scored_steps, key=lambda step: step["importance"], reverse=True)


def extract_critical(
    scored_steps: list[dict[str, Any]],
    threshold: float = CRITICAL_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return critical steps in their original order."""

    return [step for step in scored_steps if step["importance"] >= threshold]


def trim_flow(scored_steps: list[dict[str, Any]], max_steps: int | None) -> list[dict[str, Any]]:
    """Trim low-importance steps first while preserving critical steps and order."""

    if max_steps is None or len(scored_steps) <= max_steps:
        return scored_steps

    critical_indexes = {
        index
        for index, step in enumerate(scored_steps)
        if step["importance"] >= CRITICAL_THRESHOLD
    }
    if len(critical_indexes) >= max_steps:
        return [
            step for index, step in enumerate(scored_steps) if index in critical_indexes
        ]

    slots_left = max_steps - len(critical_indexes)
    noncritical_ranked = sorted(
        (
            (index, step)
            for index, step in enumerate(scored_steps)
            if index not in critical_indexes
        ),
        key=lambda item: item[1]["importance"],
        reverse=True,
    )
    kept_indexes = set(critical_indexes)
    kept_indexes.update(index for index, _step in noncritical_ranked[:slots_left])

    return [step for index, step in enumerate(scored_steps) if index in kept_indexes]
