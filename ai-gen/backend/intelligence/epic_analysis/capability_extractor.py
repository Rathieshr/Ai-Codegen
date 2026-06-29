from __future__ import annotations

from typing import Any

from .epic_analysis import CapabilityCandidate
from .repository_evidence_collector import collect_repository_evidence


CANONICAL_CAPABILITIES = [
    "Operational Awareness",
    "Fault Monitoring",
    "Alert Management",
    "Outage Investigation",
    "Reliability Analytics",
    "Asset Health",
    "Telemetry",
    "Firmware Management",
    "Device Management",
]


def extract_required_capabilities(
    epic: dict[str, Any],
    profile: dict[str, Any],
    business_problems: list[str],
    business_goals: list[str],
    intent_keywords: list[str],
) -> list[CapabilityCandidate]:
    corpus = _corpus(epic, profile, business_problems, business_goals, intent_keywords)
    candidates: list[CapabilityCandidate] = []
    for capability in CANONICAL_CAPABILITIES:
        score, reason = _capability_score(capability, corpus)
        evidence = collect_repository_evidence(capability, profile)
        if evidence:
            score += 0.08
        if score >= 0.5:
            candidates.append(CapabilityCandidate(capability, reason, min(score, 0.96), evidence))
    if not candidates:
        candidates.append(
            CapabilityCandidate(
                "Operational Awareness",
                "Default capability selected because the epic needs a business-level planning boundary.",
                0.52,
                collect_repository_evidence("Operational Awareness", profile),
            )
        )
    return _dedupe(candidates)


def extract_excluded_capabilities(epic: dict[str, Any], profile: dict[str, Any], required: list[CapabilityCandidate]) -> list[CapabilityCandidate]:
    corpus = _corpus(epic, profile, [], [], [])
    required_names = {item.name for item in required}
    excluded: list[CapabilityCandidate] = []
    exclusions = {
        "Firmware Management": ["firmware", "upgrade", "rollout", "rollback", "version"],
        "Authentication": ["login", "token", "session", "password", "otp", "authorization"],
        "Device Management": ["registration", "provision", "device onboarding"],
        "Billing": ["billing", "invoice", "payment"],
        "User Administration": ["user administration", "user management", "admin user"],
    }
    for capability, required_tokens in exclusions.items():
        if capability in required_names:
            continue
        if not any(token in corpus for token in required_tokens):
            excluded.append(
                CapabilityCandidate(
                    capability,
                    f"Epic intent does not mention {', '.join(required_tokens[:4])}; keep out of downstream feature generation.",
                    0.82,
                    collect_repository_evidence(capability, profile),
                )
            )
    return excluded


def _capability_score(capability: str, corpus: str) -> tuple[float, str]:
    rules = {
        "Operational Awareness": (["dashboard", "live", "status", "visibility", "operation", "monitoring"], "Epic needs unified operational visibility."),
        "Fault Monitoring": (["fault", "critical", "event", "severity"], "Epic needs fault event detection and review."),
        "Alert Management": (["alert", "notification", "response", "escalation"], "Epic needs actionable alert response."),
        "Outage Investigation": (["outage", "investigation", "triage", "root cause", "timeline"], "Epic needs outage investigation support."),
        "Reliability Analytics": (["analytics", "trend", "metric", "kpi", "reliability", "historical"], "Epic needs reliability trend analysis."),
        "Asset Health": (["asset", "device health", "health", "condition"], "Epic needs correlated device or asset health context."),
        "Telemetry": (["telemetry", "signal", "freshness"], "Epic needs trusted telemetry context."),
        "Firmware Management": (["firmware", "upgrade", "rollout", "rollback"], "Epic explicitly includes firmware rollout visibility."),
        "Device Management": (["device registration", "provision", "onboarding"], "Epic explicitly includes device management."),
    }
    tokens, reason = rules.get(capability, ([], f"Epic mentions {capability}."))
    hits = [token for token in tokens if token in corpus]
    if capability == "Alert Management" and any(token in corpus for token in ["fault", "critical", "event", "severity"]):
        hits = list(dict.fromkeys([*hits, "fault-response"]))
        reason = "Critical fault monitoring requires actionable alert response."
    if not hits:
        return 0.0, reason
    return 0.48 + min(len(hits), 4) * 0.1, reason


def _corpus(epic: dict[str, Any], profile: dict[str, Any], problems: list[str], goals: list[str], keywords: list[str]) -> str:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    parts = [
        epic.get("title"),
        epic.get("description"),
        profile.get("project_description"),
        " ".join(problems),
        " ".join(goals),
        " ".join(keywords),
        " ".join(str(item) for item in registry.get("modules", []) if item),
        " ".join(str(item) for item in registry.get("flows", []) if item),
    ]
    return " ".join(str(part or "").lower() for part in parts if part)


def _dedupe(candidates: list[CapabilityCandidate]) -> list[CapabilityCandidate]:
    output: list[CapabilityCandidate] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True):
        if item.name not in seen:
            output.append(item)
            seen.add(item.name)
    return output[:8]
