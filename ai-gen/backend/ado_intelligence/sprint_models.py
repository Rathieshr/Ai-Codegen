"""Canonical sprint intelligence report model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SprintIntelligenceReport:
    report_id: str
    project_id: str
    iteration_id: str
    iteration: dict[str, Any]
    health: str
    completion_confidence: dict[str, Any]
    forecast: dict[str, Any]
    metrics: dict[str, Any]
    burndown_series: list[dict[str, Any]]
    current_blockers: list[dict[str, Any]]
    delivery_risks: list[dict[str, Any]]
    recommended_interventions: list[str]
    evidence: list[dict[str, Any]]
    generated_at: str
    privacy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {
            "reportId": value["report_id"], "projectId": value["project_id"],
            "iterationId": value["iteration_id"], "iteration": value["iteration"],
            "health": value["health"], "completionConfidence": value["completion_confidence"],
            "forecast": value["forecast"], "metrics": value["metrics"],
            "burndownSeries": value["burndown_series"], "currentBlockers": value["current_blockers"],
            "deliveryRisks": value["delivery_risks"], "recommendedInterventions": value["recommended_interventions"],
            "evidence": value["evidence"], "privacy": value["privacy"], "generatedAt": value["generated_at"],
        }
