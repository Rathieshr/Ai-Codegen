"""User feedback collection for continuous improvement."""

from __future__ import annotations

from typing import Any

from .types import normalize_feedback


class FeedbackEngine:
    def record(self, feedback_items: list[dict[str, Any]], feedback: dict[str, Any]) -> dict[str, Any]:
        stored = normalize_feedback(feedback)
        feedback_items.append(stored)
        return stored

    def summary(self, feedback_items: list[dict[str, Any]]) -> dict[str, Any]:
        by_rating: dict[str, int] = {"thumbs_up": 0, "thumbs_down": 0, "neutral": 0}
        by_category: dict[str, int] = {}
        for item in feedback_items:
            rating = str(item.get("rating") or "neutral")
            category = str(item.get("category") or "General")
            by_rating[rating] = by_rating.get(rating, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1
        total = len(feedback_items)
        satisfaction = round((by_rating.get("thumbs_up", 0) / total) * 100, 2) if total else 0
        return {"feedback": feedback_items, "count": total, "byRating": by_rating, "byCategory": by_category, "satisfaction": satisfaction}
