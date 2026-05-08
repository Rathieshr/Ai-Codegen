"""Strict validation for model-suggested refinement JSON."""

from __future__ import annotations

import re
from typing import Any


ALLOWED_CONFIDENCE = {"low", "medium", "high"}
SUSPICIOUS_COMMANDS = ("rm ", "git reset", "curl ", "wget ", "npm ", "pip ", "python ", "bash ", "sh ")
SUSPICIOUS_PATH_PATTERN = re.compile(
    r"(^|[\s])([A-Za-z]:\\|/|\.?/|[A-Za-z0-9_.-]+/).+\.[A-Za-z0-9]{1,8}\b"
)


def validate_task_refinement(raw: dict) -> dict:
    """Normalize and sanitize model refinement JSON."""

    if not isinstance(raw, dict):
        raw = {}

    return {
        "base_flow": _string(raw.get("base_flow")),
        "variant": _string(raw.get("variant")),
        "surface": _string(raw.get("surface")),
        "fields": _clean_list(raw.get("fields"), limit=10),
        "validations": _clean_list(raw.get("validations"), limit=10),
        "first_pass_scope": _clean_list(raw.get("first_pass_scope"), limit=8),
        "unknowns": _clean_list(raw.get("unknowns"), limit=8),
        "confidence": _confidence(raw.get("confidence")),
    }


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or _is_suspicious(text):
        return None
    return text[:120]


def _clean_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text or _is_suspicious(text):
            continue
        if text not in cleaned:
            cleaned.append(text[:160])
        if len(cleaned) >= limit:
            break
    return cleaned


def _confidence(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in ALLOWED_CONFIDENCE else "low"


def _is_suspicious(value: str) -> bool:
    lower = value.lower()
    if any(command in lower for command in SUSPICIOUS_COMMANDS):
        return True
    if "```" in value or "# task" in lower or "# execution" in lower:
        return True
    if SUSPICIOUS_PATH_PATTERN.search(value):
        return True
    return False
