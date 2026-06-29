from __future__ import annotations

from typing import Any


def extract_business_problems(epic: dict[str, Any], profile: dict[str, Any], intent_keywords: list[str]) -> list[str]:
    text = _corpus(epic, profile, intent_keywords)
    problems: list[str] = []
    if any(token in text for token in ["dashboard", "live", "status", "visibility", "operation"]):
        problems.append("Operators lack unified operational visibility across active events, assets, and response status.")
    if any(token in text for token in ["fault", "event", "critical"]):
        problems.append("Fault information is fragmented, making critical events harder to detect and review quickly.")
    if any(token in text for token in ["alert", "notification", "response", "escalation"]):
        problems.append("Alert response is delayed because operators cannot consistently identify events needing immediate action.")
    if any(token in text for token in ["outage", "investigation", "triage", "root cause"]):
        problems.append("Outage investigation requires manual correlation of event, telemetry, and device health context.")
    if any(token in text for token in ["analytics", "trend", "reliability", "metric", "kpi"]):
        problems.append("Historical reliability trends are difficult to access and use for operational prioritization.")
    if not problems:
        domain = _clean(profile.get("domain")) or "the project domain"
        problems.append(f"Teams need clearer planning boundaries and measurable outcomes for {domain}.")
    return _unique(problems)


def _corpus(epic: dict[str, Any], profile: dict[str, Any], keywords: list[str]) -> str:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    parts = [
        epic.get("title"),
        epic.get("description"),
        profile.get("project_description"),
        " ".join(keywords),
        " ".join(str(item) for item in registry.get("modules", []) if item),
        " ".join(str(item) for item in registry.get("flows", []) if item),
    ]
    return " ".join(_clean(part).lower() for part in parts if _clean(part))


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
