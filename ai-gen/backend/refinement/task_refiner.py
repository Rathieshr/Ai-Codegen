"""Backend-only structured task refinement using an optional provider."""

from __future__ import annotations

import json
from typing import Any

from backend.refinement.provider import get_refinement_provider
from backend.refinement.schema_validator import validate_task_refinement


SYSTEM_PROMPT = (
    "You are ai-gen's backend task refinement engine. Return strict JSON only. "
    "You refine vague software work items into structured engineering metadata. "
    "You do not write code, do not invent files, and do not generate final prompts."
)

EXPECTED_SCHEMA = {
    "base_flow": "string|null",
    "variant": "string|null",
    "surface": "string|null",
    "fields": ["string"],
    "validations": ["string"],
    "first_pass_scope": ["string"],
    "unknowns": ["string"],
    "confidence": "low|medium|high",
}


def refine_task(query: str, context: dict | None = None) -> dict[str, Any]:
    """Return structured refinement metadata or a safe disabled fallback."""

    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled():
        return {
            "refinement_used": False,
            "refinement_reason": "provider unavailable",
            "refinement": _empty_refinement(),
        }

    payload = {
        "query": query,
        "source": (context or {}).get("source"),
        "work_item": (context or {}).get("work_item"),
        "detected_intent": (context or {}).get("intent"),
        "detected_flow": (context or {}).get("detected_flow"),
        "constraints": (context or {}).get("constraints", []),
        "repo_hints": (context or {}).get("repo_hints", {}),
        "expected_json_schema": EXPECTED_SCHEMA,
    }
    raw = provider.refine_json(
        SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=True),
        max_tokens=800,
    )
    validated = validate_task_refinement(raw)
    if not any(
        validated.get(key)
        for key in ("base_flow", "variant", "surface", "fields", "validations", "first_pass_scope", "unknowns")
    ):
        return {
            "refinement_used": False,
            "refinement_reason": "provider returned no usable refinement",
            "refinement": validated,
        }

    return {
        "refinement_used": True,
        "refinement_reason": "provider returned structured refinement",
        "refinement": validated,
    }


def _empty_refinement() -> dict[str, Any]:
    return validate_task_refinement({})
