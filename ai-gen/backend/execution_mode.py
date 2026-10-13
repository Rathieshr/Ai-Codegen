"""Prompt mode and execution confidence selection for ai-gen."""

from __future__ import annotations

from typing import Any


RESPOND_KEYWORDS = ("explain", "summarize", "understand", "what does", "how does", "describe")
IMPLEMENTATION_KEYWORDS = ("fix", "implement", "generate", "modify", "add", "build", "create")
ARCHITECTURE_KEYWORDS = ("architecture", "re-architect", "migration", "strategy", "system design")


def score_execution_confidence(
    intent: str | None,
    matched_logic: str | None,
    detected_flow: str | None,
    related_flows: list | None,
    planning_enabled: bool,
    retrieval_bias_applied: bool,
    likely_bug_hotspots: list | None,
    critical_constraints: list | None,
) -> dict[str, Any]:
    """Score whether ai-gen has enough selected context for compact execution."""

    score = 0.0
    signals: list[str] = []
    if matched_logic:
        score += 0.2
        signals.append("matched logic present")
    if detected_flow:
        score += 0.2
        signals.append("detected flow present")
    if retrieval_bias_applied:
        score += 0.1
        signals.append("retrieval bias applied")
    if planning_enabled:
        score += 0.1
        signals.append("planning available")
    if critical_constraints:
        score += 0.15
        signals.append("constraints available")
    if likely_bug_hotspots:
        score += 0.15
        signals.append("bug hotspots available")
    if related_flows:
        score += 0.1
        signals.append("related flows available")
    if intent in {"feature", "bug_fix", "refactor"}:
        score += 0.05
        signals.append(f"intent is {intent}")

    score = min(max(score, 0.0), 1.0)
    return {
        "score": round(score, 2),
        "level": _confidence_level(score),
        "signals": signals,
    }


def detect_prompt_mode(
    query: str,
    intent: str | None,
    matched_logic: str | None,
    detected_flow: str | None,
    retrieval_bias_applied: bool = False,
    likely_bug_hotspots: list | None = None,
    planning_enabled: bool = False,
    related_flows: list | None = None,
) -> dict[str, str]:
    """Choose whether the final prompt should ask for response, execution, or exploration."""

    normalized = query.lower()
    if any(keyword in normalized for keyword in RESPOND_KEYWORDS):
        return {"mode": "respond", "reason": "explanation task should produce a concise answer"}

    if any(keyword in normalized for keyword in ARCHITECTURE_KEYWORDS) and not (matched_logic and detected_flow):
        return {"mode": "explore", "reason": "architecture task has weak selected context"}

    has_implementation_signal = intent in {"bug_fix", "feature", "refactor"} or any(
        keyword in normalized for keyword in IMPLEMENTATION_KEYWORDS
    )
    has_selected_context = bool(
        matched_logic
        and (detected_flow or retrieval_bias_applied or planning_enabled or likely_bug_hotspots or related_flows)
    )
    if has_implementation_signal and has_selected_context:
        return {"mode": "execute", "reason": "high-confidence context available"}

    return {"mode": "explore", "reason": "context confidence is weak or task is ambiguous"}


def _confidence_level(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"
