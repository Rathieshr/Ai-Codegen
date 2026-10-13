"""Deterministic HEI provider-routing rules."""

from __future__ import annotations

from typing import Any


ROUTING_PRIORITIES: dict[str, tuple[str, ...]] = {
    "coding": ("codex", "claude"),
    "architecture": ("gpt", "claude"),
    "ui": ("gemini", "gpt"),
    "documentation": ("gpt", "claude"),
    "large_context": ("claude", "gemini"),
    "local": ("ollama",),
}

ROUTING_RULES = (
    {"target": "Coding", "models": ["Codex", "Claude Code (Claude model profile)"]},
    {"target": "Architecture", "models": ["GPT"]},
    {"target": "UI", "models": ["Gemini"]},
    {"target": "Documentation", "models": ["GPT"]},
    {"target": "Large Context", "models": ["Claude"]},
    {"target": "Local", "models": ["Ollama"]},
)

_MODEL_ALIASES = {
    "claude code": "claude",
    "claude-code": "claude",
    "claude_code": "claude",
    "openai": "gpt",
    "local": "ollama",
}


def normalize_model_id(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    return _MODEL_ALIASES.get(normalized, normalized)


def resolve_target(target_task: Any, execution_mode: str) -> tuple[str, str]:
    task = target_task if isinstance(target_task, dict) else {"description": str(target_task or "")}
    if task.get("localOnly") is True:
        return "local", "Target Task requires local execution."
    if task.get("requiresLargeContext") is True:
        return "large_context", "Target Task explicitly requires large context."

    explicit = _target_alias(task.get("category") or task.get("type") or task.get("target"))
    if explicit:
        return explicit, f"Target Task explicitly selected {explicit.replace('_', ' ')} routing."

    text = " ".join(str(task.get(field) or "") for field in ("title", "description", "objective", "workArea")).casefold()
    keyword_groups = (
        ("local", ("local only", "offline", "private model", "on-device")),
        ("large_context", ("large context", "monorepo", "cross-repository", "whole repository")),
        ("ui", (" ui ", "frontend", "screen", "viewmodel", "xaml", "react", "css", "layout")),
        ("architecture", ("architecture", "system design", "adr", "service boundary")),
        ("documentation", ("documentation", "readme", "runbook", "guide", "release notes")),
    )
    padded = f" {text} "
    for target, keywords in keyword_groups:
        if any(keyword in padded for keyword in keywords):
            return target, f"Target Task language matched the {target.replace('_', ' ')} routing rule."

    mode_target = _target_alias(execution_mode)
    if mode_target in {"architecture", "documentation"}:
        return mode_target, f"Execution Mode selected {mode_target} routing."
    return "coding", "Target Task defaults to coding routing."


def optimizer_mode(execution_mode: str, target: str) -> str:
    normalized = "_".join(str(execution_mode or "").strip().casefold().replace("-", " ").split())
    aliases = {"bugfix": "bug_fix", "implement": "implementation", "coding": "implementation", "ui": "implementation"}
    normalized = aliases.get(normalized, normalized)
    supported = {"implementation", "bug_fix", "refactor", "architecture", "review", "documentation", "testing", "optimization"}
    if normalized in supported:
        return normalized
    return target if target in {"architecture", "documentation"} else "implementation"


def _target_alias(value: Any) -> str:
    normalized = "_".join(str(value or "").strip().casefold().replace("-", " ").split())
    aliases = {
        "code": "coding",
        "implementation": "coding",
        "bug_fix": "coding",
        "refactor": "coding",
        "frontend": "ui",
        "ux": "ui",
        "docs": "documentation",
        "large": "large_context",
        "offline": "local",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in ROUTING_PRIORITIES else ""
