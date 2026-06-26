from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

WorkItemType = Literal["Epic", "Feature", "Story", "Task"]


@dataclass(frozen=True)
class IntentModel:
    work_item_id: int | str | None
    work_item_type: WorkItemType
    business_goal: str
    user_goal: str
    primary_capability: str
    secondary_capabilities: list[str] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)
    business_domain: str = ""
    business_keywords: list[str] = field(default_factory=list)
    technical_keywords: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    inferred_modules: list[str] = field(default_factory=list)
    inferred_flows: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: list[str] = field(default_factory=list)
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "workItemId": self.work_item_id,
            "workItemType": self.work_item_type,
            "businessGoal": self.business_goal,
            "userGoal": self.user_goal,
            "primaryCapability": self.primary_capability,
            "secondaryCapabilities": self.secondary_capabilities,
            "personas": self.personas,
            "businessDomain": self.business_domain,
            "businessKeywords": self.business_keywords,
            "technicalKeywords": self.technical_keywords,
            "actions": self.actions,
            "entities": self.entities,
            "inferredModules": self.inferred_modules,
            "inferredFlows": self.inferred_flows,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "extractedAt": self.extracted_at,
        }

