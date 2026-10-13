"""Engineering scorecard generation."""

from __future__ import annotations

from typing import Any

from .types import clamp, number


class EngineeringScorecard:
    def build(
        self,
        compliance: dict[str, Any],
        metrics: dict[str, Any],
        feedback: dict[str, Any],
        observability: dict[str, Any],
    ) -> dict[str, Any]:
        compliance_scores = compliance.get("scores") if isinstance(compliance.get("scores"), dict) else {}
        planning = number(compliance_scores.get("planning"), 75)
        execution = (number(compliance_scores.get("repository"), 75) + number(metrics.get("promptSuccess"), 75) + number(metrics.get("averageReadiness"), 75)) / 3
        qa = (number(compliance_scores.get("qa"), 75) + number(metrics.get("averageCoverage"), 75)) / 2
        repository = number(compliance_scores.get("repository"), 75)
        memory = number(metrics.get("memoryReuse"), 0)
        velocity = self._velocity(metrics)
        release = (qa + number(compliance_scores.get("release"), 75)) / 2
        health = clamp((planning + execution + qa + repository + max(memory, 50) + velocity + release) / 7)
        return {
            "planningQuality": round(clamp(planning), 2),
            "executionQuality": round(clamp(execution), 2),
            "qaQuality": round(clamp(qa), 2),
            "repositoryHealth": round(clamp(repository), 2),
            "memoryReuse": round(clamp(memory), 2),
            "engineeringVelocity": round(clamp(velocity), 2),
            "releaseReadiness": round(clamp(release), 2),
            "overallEngineeringHealth": round(health, 2),
            "status": "Healthy" if health >= 85 else "Needs Attention" if health >= 70 else "At Risk",
            "feedbackSatisfaction": feedback.get("satisfaction", 0),
            "observabilityFailures": observability.get("failureCount", 0),
        }

    def _velocity(self, metrics: dict[str, Any]) -> float:
        times = [
            number(metrics.get("planningTime"), 0),
            number(metrics.get("executionTime"), 0),
            number(metrics.get("qaTime"), 0),
            number(metrics.get("approvalTime"), 0),
        ]
        captured = [item for item in times if item > 0]
        if not captured:
            return 75
        average = sum(captured) / len(captured)
        return clamp(100 - min(50, average / 60000))
