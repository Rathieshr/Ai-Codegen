from __future__ import annotations

from typing import Iterable


CONCEPT_EXPANSIONS: dict[str, list[str]] = {
    "alarm": ["alert", "notification", "incident", "event", "escalation", "acknowledgement", "history", "audit"],
    "alert": ["alarm", "notification", "incident", "escalation", "priority", "acknowledgement"],
    "notification": ["alert", "subscription", "delivery", "message", "acknowledgement", "history", "audit"],
    "event": ["incident", "timeline", "priority", "history", "lifecycle", "status"],
    "dashboard": ["visibility", "monitoring", "operations", "status", "workspace"],
    "operations": ["operator", "response", "monitoring", "status", "review"],
    "device": ["equipment", "fleet", "status", "management"],
    "health": ["condition", "telemetry", "monitoring", "status", "analysis"],
    "firmware": ["upgrade", "rollback", "deployment", "compliance", "version"],
    "rollout": ["deployment", "upgrade", "release", "distribution", "compliance"],
    "admin": ["user", "identity", "role", "permission", "audit", "access"],
    "analytics": ["reporting", "trend", "kpi", "metric", "insight", "telemetry"],
    "trend": ["analytics", "reporting", "forecast", "history", "metric"],
    "telemetry": ["signal", "reading", "freshness", "monitoring", "analysis"],
}


def expand_concepts(values: Iterable[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        if not cleaned:
            continue
        for token in _variants(cleaned):
            key = token.lower()
            if key not in seen:
                expanded.append(token)
                seen.add(key)
    return expanded


def _variants(value: str) -> list[str]:
    variants = [value]
    for token in _tokenize(value):
        if token not in variants:
            variants.append(token)
        for expanded in CONCEPT_EXPANSIONS.get(token, []):
            if expanded not in variants:
                variants.append(expanded)
    return variants


def _tokenize(value: str) -> list[str]:
    return [
        token.strip(" ,.:;()[]{}").lower()
        for token in value.replace("/", " ").replace("-", " ").replace("_", " ").split()
        if token.strip(" ,.:;()[]{}")
    ]


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())
