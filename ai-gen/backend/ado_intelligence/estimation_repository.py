"""Persistence for estimates, outcomes, and calibration history."""

from __future__ import annotations

from threading import RLock
from typing import Any

from backend.platform.shared import JsonMapStore

from .estimation_models import EstimationRecommendation
from .models import now_iso


class EstimationRepository:
    def __init__(self, estimates: JsonMapStore, outcomes: JsonMapStore) -> None:
        self.estimates = estimates
        self.outcomes = outcomes
        self._lock = RLock()

    def save(self, estimate: EstimationRecommendation) -> dict[str, Any]:
        with self._lock:
            values = self.estimates.read()
            estimate.updated_at = now_iso()
            values[estimate.estimate_id] = estimate.to_dict()
            self.estimates.write(values)
        return estimate.to_dict()

    def get(self, estimate_id: str) -> EstimationRecommendation | None:
        value = self.estimates.read().get(estimate_id)
        return EstimationRecommendation.from_dict(value) if isinstance(value, dict) else None

    def latest(self, work_item_id: str) -> EstimationRecommendation | None:
        items = [EstimationRecommendation.from_dict(item) for item in self.estimates.read().values() if isinstance(item, dict) and str(item.get("workItemId")) == str(work_item_id)]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[0] if items else None

    def list_project(self, project_id: str, team_id: str = "") -> list[EstimationRecommendation]:
        return [
            EstimationRecommendation.from_dict(item) for item in self.estimates.read().values()
            if isinstance(item, dict) and str(item.get("projectId")) == str(project_id)
            and (not team_id or str(item.get("teamId")) == str(team_id))
        ]

    def save_outcome(self, estimate_id: str, value: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            outcomes = self.outcomes.read()
            record = {**value, "estimateId": estimate_id, "recordedAt": now_iso()}
            outcomes[estimate_id] = record
            self.outcomes.write(outcomes)
        return record

    def get_outcome(self, estimate_id: str) -> dict[str, Any] | None:
        value = self.outcomes.read().get(estimate_id)
        return value if isinstance(value, dict) else None

    def project_outcomes(self, project_id: str, team_id: str = "") -> list[tuple[EstimationRecommendation, dict[str, Any]]]:
        result = []
        for estimate in self.list_project(project_id, team_id):
            outcome = self.get_outcome(estimate.estimate_id)
            if outcome:
                result.append((estimate, outcome))
        return result
