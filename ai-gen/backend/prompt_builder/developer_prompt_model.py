"""Developer Prompt V2 data helpers."""

from __future__ import annotations

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
        return unique([clean(value.get("name") or value.get("title") or value.get("rule") or value.get("risk"))])
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                result.append(clean(item.get("name") or item.get("title") or item.get("rule") or item.get("risk") or item.get("acceptanceText")))
            else:
                result.extend(string_list(item))
        return unique([item for item in result if item])
    return [clean(value)] if clean(value) else []


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result
