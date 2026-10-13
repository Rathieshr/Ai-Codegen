"""Deterministic MVP execution target routing."""

from __future__ import annotations

import os
import shutil


EXPLAIN_WORDS = {"explain", "summarize", "understand", "flow"}
IMPLEMENT_WORDS = {"fix", "implement", "generate", "modify", "add"}
DESIGN_WORDS = {"design", "architecture", "re-architect", "migration", "cross-platform", "strategy"}
UI_WORDS = {"screen", "page", "dashboard", "ui", "layout", "component", "widget", "form"}
SUPPORTED_TARGETS = {"local", "cloud", "codex", "preview_only"}


def get_available_targets() -> dict:
    """Return simple availability flags for routing targets."""

    return {
        "local": os.getenv("AI_GEN_LOCAL_ENABLED") == "1",
        "cloud": os.getenv("AI_GEN_CLOUD_ENABLED") == "1",
        "codex": os.getenv("AI_GEN_CODEX_ENABLED") == "1" or shutil.which("codex") is not None,
    }


def detect_execution_target(
    query: str,
    intent: str | None,
    context_size: int | None = None,
    routing_mode: str = "auto",
) -> dict:
    """Choose an execution target without calling any provider."""

    available_targets = get_available_targets()
    normalized_mode = routing_mode if routing_mode in SUPPORTED_TARGETS else "auto"

    if normalized_mode in {"local", "cloud", "codex"}:
        return _forced_route(normalized_mode, available_targets)

    query_words = set(query.lower().replace("-", " ").split())
    original_query = query.lower()

    if _contains_any(original_query, query_words, UI_WORDS):
        return _route_if_available(
            preferred_target="codex",
            available_targets=available_targets,
            reason="UI implementation task requires repo-facing execution",
        )
    if _contains_any(original_query, query_words, DESIGN_WORDS):
        return _route_if_available(
            preferred_target="cloud",
            available_targets=available_targets,
            reason="architecture or strategy task may benefit from cloud planning",
        )
    if _contains_any(original_query, query_words, IMPLEMENT_WORDS) or intent in {"bug_fix", "feature"}:
        return _route_if_available(
            preferred_target="codex",
            available_targets=available_targets,
            reason="implementation task requires repo-facing execution",
        )
    if _contains_any(original_query, query_words, EXPLAIN_WORDS):
        return _route_if_available(
            preferred_target="local",
            available_targets=available_targets,
            reason="explanation task can use local context review",
        )

    return {
        "target": "preview_only",
        "reason": "no execution target matched; preview only",
    }


def _forced_route(target: str, available_targets: dict) -> dict:
    """Route to an explicitly requested target if available."""

    if available_targets.get(target):
        return {
            "target": target,
            "reason": f"routing_mode forced {target}",
        }
    return {
        "target": "preview_only",
        "reason": f"routing_mode forced {target}, but {target} is unavailable",
    }


def _route_if_available(preferred_target: str, available_targets: dict, reason: str) -> dict:
    """Use a preferred target when available, otherwise fall back to preview."""

    if available_targets.get(preferred_target):
        return {
            "target": preferred_target,
            "reason": reason,
        }
    return {
        "target": "preview_only",
        "reason": f"{reason}; {preferred_target} unavailable",
    }


def _contains_any(query: str, query_words: set[str], keywords: set[str]) -> bool:
    """Match both single-word and hyphenated/multi-part keywords deterministically."""

    return any(keyword in query_words or keyword in query for keyword in keywords)
