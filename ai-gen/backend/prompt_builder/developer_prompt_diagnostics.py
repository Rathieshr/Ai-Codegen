"""Diagnostics helpers for Developer Prompt V2."""

from __future__ import annotations

from typing import Any


def developer_prompt_diagnostics(
    *,
    budget_result: dict[str, Any],
    warnings: list[str],
    section_count: int,
    package_id: str,
) -> dict[str, Any]:
    diagnostics = budget_result.get("diagnostics") if isinstance(budget_result.get("diagnostics"), dict) else {}
    return {
        "packageId": package_id,
        "sectionCount": section_count,
        "provider": diagnostics.get("provider"),
        "model": diagnostics.get("model"),
        "contextLimit": diagnostics.get("contextLimit"),
        "reservedOutputTokens": diagnostics.get("reservedOutputTokens"),
        "inputBudget": diagnostics.get("inputBudget"),
        "finalPromptTokens": diagnostics.get("finalPromptTokens"),
        "compressionApplied": bool(diagnostics.get("compressionApplied")),
        "removedSections": diagnostics.get("removedSections", []),
        "largestSection": diagnostics.get("largestSection", {}),
        "blockedByBudgetGuard": bool(diagnostics.get("blockedByBudgetGuard")),
        "promptBudgetProfile": diagnostics.get("budget_profile_name") or diagnostics.get("promptBudgetProfile"),
        "sectionTokens": diagnostics.get("section_tokens", {}),
        "warnings": warnings,
    }
