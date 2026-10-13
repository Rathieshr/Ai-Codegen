"""Shared helpers for Implementation Validation V1."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("\n", ",").split(",")]
        return unique([part for part in parts if part])
    if isinstance(value, dict):
        return unique([clean(value.get("path") or value.get("name") or value.get("title") or value.get("file"))])
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(string_list(item))
        return unique([item for item in result if item])
    text = clean(value)
    return [text] if text else []


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = clean(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def stable_id(prefix: str, payload: Any) -> str:
    digest = hashlib.sha1(str(payload).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def score_from_results(results: list[dict[str, Any]], positive_statuses: set[str]) -> int:
    if not results:
        return 0
    total = 0.0
    for item in results:
        status = clean(item.get("status")).lower()
        if status in positive_statuses:
            total += 1.0
        elif status in {"partially implemented", "partial", "partially covered", "needsreview", "needs review"}:
            total += 0.5
    return round((total / len(results)) * 100)


def violation(
    *,
    rule: str,
    severity: str,
    message: str,
    file_path: str = "",
    recommendation: str = "",
    category: str = "",
) -> dict[str, Any]:
    return {
        "rule": rule,
        "severity": severity,
        "category": category or rule,
        "message": message,
        "file": file_path,
        "recommendation": recommendation,
    }


def lower_blob(*values: Any) -> str:
    return " ".join(clean(value).casefold() for value in values if clean(value))
