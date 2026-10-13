"""Persistent estimate, override, and learning records."""

from __future__ import annotations

from typing import Any

from backend.platform.shared import JsonMapStore


class EngineeringEstimationRepository:
    def __init__(self, estimates: JsonMapStore, outcomes: JsonMapStore) -> None:
        self.estimates = estimates
        self.outcomes = outcomes

    def save(self, estimate: dict[str, Any]) -> dict[str, Any]:
        values = self.estimates.read()
        values[str(estimate["estimateId"])] = estimate
        self.estimates.write(values)
        return estimate

    def get(self, estimate_id: str) -> dict[str, Any] | None:
        value = self.estimates.read().get(str(estimate_id))
        return dict(value) if isinstance(value, dict) else None

    def latest(self, artifact_id: str) -> dict[str, Any] | None:
        values = [dict(value) for value in self.estimates.read().values() if isinstance(value, dict) and str(value.get("artifactId")) == str(artifact_id)]
        return max(values, key=lambda value: (int(value.get("version") or 0), str(value.get("updatedAt") or "")), default=None)

    def list_project(self, project_id: str) -> list[dict[str, Any]]:
        return [dict(value) for value in self.estimates.read().values() if isinstance(value, dict) and (not project_id or str(value.get("projectId")) == str(project_id))]

    def save_outcome(self, estimate_id: str, outcome: dict[str, Any]) -> dict[str, Any]:
        values = self.outcomes.read()
        values[str(estimate_id)] = outcome
        self.outcomes.write(values)
        return outcome

    def outcome(self, estimate_id: str) -> dict[str, Any] | None:
        value = self.outcomes.read().get(str(estimate_id))
        return dict(value) if isinstance(value, dict) else None
