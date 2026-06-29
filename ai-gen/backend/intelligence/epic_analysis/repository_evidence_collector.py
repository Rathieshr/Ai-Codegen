from __future__ import annotations

from typing import Any


def collect_repository_evidence(capability: str, profile: dict[str, Any], repository_snapshot: dict[str, Any] | None = None) -> list[str]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    candidates = [
        *[str(item) for item in registry.get("modules", []) if item],
        *[str(item) for item in registry.get("flows", []) if item],
        *[str(item) for item in registry.get("components", []) if item],
        *[str(item) for item in registry.get("source_files", []) if item],
    ]
    snapshot = repository_snapshot or {}
    candidates.extend(str(item) for item in snapshot.get("source_files", []) if item)
    candidates.extend(str(item.get("path") or item.get("name")) for item in snapshot.get("rankedFiles", []) if isinstance(item, dict))
    tokens = _capability_tokens(capability)
    evidence = [item for item in _unique(candidates) if any(token in item.lower() for token in tokens)]
    return evidence[:6]


def collect_all_repository_evidence(profile: dict[str, Any]) -> list[dict[str, Any]]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    evidence: list[dict[str, Any]] = []
    for key in ["modules", "flows", "components", "source_files", "standards"]:
        for item in registry.get(key, []) if isinstance(registry.get(key), list) else []:
            name = str(item.get("name") if isinstance(item, dict) else item).strip()
            if name:
                evidence.append({"type": key[:-1] if key.endswith("s") else key, "name": name, "source": "knowledge_registry"})
    return evidence[:24]


def _capability_tokens(capability: str) -> list[str]:
    mapping = {
        "Operational Awareness": ["dashboard", "status", "operation", "monitor"],
        "Fault Monitoring": ["fault", "event", "telemetry", "health"],
        "Alert Management": ["alert", "notification", "audit", "escalation"],
        "Outage Investigation": ["outage", "investigation", "timeline", "health", "fault"],
        "Reliability Analytics": ["analytics", "trend", "report", "reliability", "metric"],
        "Asset Health": ["asset", "health", "device", "telemetry"],
        "Firmware Management": ["firmware", "upgrade", "rollout"],
    }
    return mapping.get(capability, [part.lower() for part in capability.split()])


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split())
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output
