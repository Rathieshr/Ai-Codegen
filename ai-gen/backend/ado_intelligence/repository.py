"""Persistent recommendation and analysis history store."""

from __future__ import annotations

from threading import RLock
from typing import Any

from backend.platform.shared import JsonMapStore

from .models import RecommendationStatus, WorkItemRecommendation


class WorkItemRecommendationRepository:
    def __init__(self, recommendations: JsonMapStore, analyses: JsonMapStore) -> None:
        self.recommendations = recommendations
        self.analyses = analyses
        self._lock = RLock()

    def save(self, recommendation: WorkItemRecommendation) -> dict[str, Any]:
        with self._lock:
            values = self.recommendations.read()
            values[recommendation.recommendation_id] = recommendation.to_dict()
            self.recommendations.write(values)
        return recommendation.to_dict()

    def get(self, recommendation_id: str) -> WorkItemRecommendation | None:
        value = self.recommendations.read().get(recommendation_id)
        return WorkItemRecommendation.from_dict(value) if isinstance(value, dict) else None

    def list(self, work_item_id: str) -> list[WorkItemRecommendation]:
        values = [WorkItemRecommendation.from_dict(item) for item in self.recommendations.read().values() if isinstance(item, dict) and str(item.get("workItemId")) == str(work_item_id)]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def list_all(self) -> list[WorkItemRecommendation]:
        values = [WorkItemRecommendation.from_dict(item) for item in self.recommendations.read().values() if isinstance(item, dict)]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def save_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            values = self.analyses.read()
            values[analysis["analysisId"]] = analysis
            self.analyses.write(values)
        return analysis

    def latest_analysis(self, work_item_id: str) -> dict[str, Any] | None:
        values = [
            item for item in self.analyses.read().values()
            if isinstance(item, dict) and str(item.get("workItemId") or "") == str(work_item_id)
        ]
        values.sort(key=lambda item: str(item.get("generatedAt") or item.get("createdAt") or ""), reverse=True)
        return values[0] if values else None

    def mark_stale(self, work_item_id: str, revision: int, *, include_same_revision: bool = False) -> int:
        changed = 0
        for item in self.list(work_item_id):
            if item.status == RecommendationStatus.STALE:
                continue
            if item.work_item_revision != revision or include_same_revision:
                item.status = RecommendationStatus.STALE
                self.save(item)
                changed += 1
        return changed
