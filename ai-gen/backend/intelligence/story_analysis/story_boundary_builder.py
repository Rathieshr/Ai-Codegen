from __future__ import annotations

from typing import Any

from .story_analysis import PlanningBoundary


def buildStoryPlanningBoundary(feature_dna: dict[str, Any], responsibilities: list[str]) -> PlanningBoundary:
    boundary = feature_dna.get("planningBoundary") if isinstance(feature_dna.get("planningBoundary"), dict) else {}
    in_scope = _string_list(boundary.get("inScope")) or responsibilities
    out_scope = _string_list(boundary.get("outOfScope"))
    if not out_scope:
        text = " ".join([feature_dna.get("capability") or "", *responsibilities]).lower()
        out_scope = ["Notifications", "Investigation", "Analytics", "Firmware"]
        if "outage" in text or "investigation" in text:
            out_scope = ["Firmware", "User login", "General analytics dashboard"]
        elif "firmware" in text:
            out_scope = ["Outage investigation", "General alerting"]
    return PlanningBoundary(in_scope=_unique(in_scope), out_of_scope=_unique(out_scope))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [" ".join(str(item).split()) for item in value if " ".join(str(item).split())]
    text = " ".join(str(value).split())
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

