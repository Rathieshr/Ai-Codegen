from __future__ import annotations

from .epic_analysis import CapabilityCandidate, CapabilityRelationship


def build_capability_relationships(capabilities: list[CapabilityCandidate]) -> list[CapabilityRelationship]:
    names = {item.name for item in capabilities}
    relationships: list[CapabilityRelationship] = []
    if {"Operational Awareness", "Alert Management"} <= names:
        relationships.append(CapabilityRelationship("Operational Awareness", "supports", "Alert Management", "Live operational status helps operators act on alerts."))
    if {"Fault Monitoring", "Outage Investigation"} <= names:
        relationships.append(CapabilityRelationship("Fault Monitoring", "supports", "Outage Investigation", "Fault events provide the entry point for outage investigation."))
    if {"Reliability Analytics", "Fault Monitoring"} <= names:
        relationships.append(CapabilityRelationship("Reliability Analytics", "depends_on", "Fault Monitoring", "Reliability trends depend on captured fault event history."))
    if {"Asset Health", "Outage Investigation"} <= names:
        relationships.append(CapabilityRelationship("Asset Health", "supports", "Outage Investigation", "Device health context improves investigation quality."))
    if {"Telemetry", "Fault Monitoring"} <= names:
        relationships.append(CapabilityRelationship("Telemetry", "supports", "Fault Monitoring", "Fault monitoring depends on trusted telemetry signals."))
    return relationships
