"""Canonical contracts for provider-neutral engineering reasoning."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ReasoningRequest:
    workflowType: str
    engineeringContext: dict[str, Any]
    userRequirement: str = ""
    providerPreference: str = "Auto"
    correlationId: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceReference:
    referenceId: str
    source: str
    name: str
    reason: str = ""


@dataclass
class ReasoningTelemetry:
    provider: str = "Deterministic"
    model: str = ""
    latencyMs: int = 0
    promptTokens: int = 0
    completionTokens: int = 0
    estimatedCost: float = 0.0
    retries: int = 0
    workflow: str = ""
    promptVersion: str = ""
    promptStored: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReasoningResult:
    workflowType: str
    recommendation: Any
    reasoning: list[str]
    alternatives: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    risks: list[str]
    tradeOffs: list[str]
    impact: dict[str, Any]
    confidence: dict[str, Any]
    reasoningMode: str
    promptVersion: str
    provider: str
    model: str
    telemetry: ReasoningTelemetry
    warnings: list[str] = field(default_factory=list)
    structuredResponse: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["telemetry"] = asdict(self.telemetry)
        return value


@dataclass(frozen=True)
class BuiltReasoningPrompt:
    prompt: str
    promptVersion: str
    sections: list[dict[str, Any]]
    evidenceCatalog: list[dict[str, Any]]
    diagnostics: dict[str, Any]
