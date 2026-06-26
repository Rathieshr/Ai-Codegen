from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

MatchType = Literal["capability", "module", "flow", "application", "dependency"]
MatchSource = Literal["intent", "repository", "knowledge_registry", "fallback_rules"]


@dataclass(frozen=True)
class CapabilityMatch:
    name: str
    type: MatchType
    confidence: float
    reason: str
    source: MatchSource
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class RejectedCapability:
    name: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "reason": self.reason, "confidence": self.confidence}


@dataclass(frozen=True)
class CapabilityContext:
    work_item_id: int | str | None
    work_item_type: str
    primary_capability: CapabilityMatch
    secondary_capabilities: list[CapabilityMatch] = field(default_factory=list)
    rejected_capabilities: list[RejectedCapability] = field(default_factory=list)
    relevant_modules: list[CapabilityMatch] = field(default_factory=list)
    relevant_flows: list[CapabilityMatch] = field(default_factory=list)
    relevant_applications: list[CapabilityMatch] = field(default_factory=list)
    relevant_dependencies: list[CapabilityMatch] = field(default_factory=list)
    capability_reasoning: list[str] = field(default_factory=list)
    confidence: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "workItemId": self.work_item_id,
            "workItemType": self.work_item_type,
            "primaryCapability": self.primary_capability.to_dict(),
            "secondaryCapabilities": [item.to_dict() for item in self.secondary_capabilities],
            "rejectedCapabilities": [item.to_dict() for item in self.rejected_capabilities],
            "relevantModules": [item.to_dict() for item in self.relevant_modules],
            "relevantFlows": [item.to_dict() for item in self.relevant_flows],
            "relevantApplications": [item.to_dict() for item in self.relevant_applications],
            "relevantDependencies": [item.to_dict() for item in self.relevant_dependencies],
            "capabilityReasoning": self.capability_reasoning,
            "confidence": self.confidence,
            "generatedAt": self.generated_at,
        }

