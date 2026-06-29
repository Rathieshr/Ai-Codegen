from __future__ import annotations

from .epic_analysis import CapabilityCandidate, CapabilityPriority


def prioritize_capabilities(capabilities: list[CapabilityCandidate]) -> list[CapabilityPriority]:
    priority_order = {
        "Fault Monitoring": ("Critical", 1),
        "Operational Awareness": ("Critical", 2),
        "Alert Management": ("High", 3),
        "Outage Investigation": ("High", 4),
        "Reliability Analytics": ("Medium", 5),
        "Asset Health": ("Medium", 6),
        "Telemetry": ("Medium", 7),
        "Firmware Management": ("Low", 8),
        "Device Management": ("Low", 9),
    }
    priorities: list[CapabilityPriority] = []
    for capability in capabilities:
        priority, rank = priority_order.get(capability.name, ("Medium", 50))
        evidence_text = "repository support" if capability.repository_evidence else "business impact"
        priorities.append(CapabilityPriority(capability.name, priority, f"Ranked by {evidence_text}, business impact, and dependency sequencing.", rank))
    return sorted(priorities, key=lambda item: item.rank)
