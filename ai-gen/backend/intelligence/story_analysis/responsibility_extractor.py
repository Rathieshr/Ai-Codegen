from __future__ import annotations

from typing import Any


DEFAULT_RESPONSIBILITIES = [
    "View records",
    "Review details",
    "Search records",
    "Filter results",
    "Handle unavailable data",
    "Audit user activity",
]


def extractBusinessResponsibilities(feature_dna: dict[str, Any], feature: dict[str, Any] | None = None) -> list[str]:
    feature = feature or {}
    candidates: list[str] = []
    candidates.extend(_string_list(feature_dna.get("responsibilities")))
    boundary = feature_dna.get("planningBoundary") if isinstance(feature_dna.get("planningBoundary"), dict) else {}
    candidates.extend(_string_list(boundary.get("inScope")))
    candidates.extend(_string_list(feature.get("responsibilities")))
    candidates.extend(_string_list(feature.get("acceptance_themes") or feature.get("acceptanceThemes")))
    if not candidates:
        title = _clean_text(feature.get("title") or feature_dna.get("capability"))
        candidates.extend(_responsibilities_from_title(title))
    return _unique([_normalize_responsibility(item) for item in candidates if _clean_text(item)])[:10] or list(DEFAULT_RESPONSIBILITIES)


def _responsibilities_from_title(title: str) -> list[str]:
    lowered = title.lower()
    if "fault" in lowered:
        return [
            "Detect fault",
            "Classify severity",
            "Review events",
            "Search fault events",
            "Filter events",
            "View event details",
            "See newly arrived events",
            "Handle unavailable event data",
            "Audit review",
        ]
    if "outage" in lowered or "investigation" in lowered:
        return ["Start investigation", "Review event timeline", "Search evidence", "Filter evidence", "Capture notes", "Review missing data"]
    if "alert" in lowered:
        return ["Receive alerts", "Review alert details", "Search alerts", "Filter alerts", "Acknowledge alerts"]
    return list(DEFAULT_RESPONSIBILITIES)


def _normalize_responsibility(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").split())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    if isinstance(value, tuple | set):
        return [_clean_text(item) for item in value if _clean_text(item)]
    text = _clean_text(value)
    return [text] if text else []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
