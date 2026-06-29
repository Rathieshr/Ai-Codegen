from __future__ import annotations

from typing import Any


def reasoning_diagnostics(
    *,
    output_type: str,
    prompt: str,
    provider_used: str,
    prompt_sections: list[str],
    duplicate_count: int,
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "outputType": output_type,
        "providerUsed": provider_used,
        "promptTokensEstimate": _estimate_tokens(prompt),
        "promptSizeChars": len(prompt),
        "promptSections": prompt_sections,
        "duplicateCandidateCount": duplicate_count,
        "validationWarnings": validation_warnings,
    }


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.25))

