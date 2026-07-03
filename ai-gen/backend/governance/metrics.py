"""Engineering metrics aggregation."""

from __future__ import annotations

from typing import Any

from .types import number


class MetricsEngine:
    def record(self, metrics: list[dict[str, Any]], metric: dict[str, Any]) -> dict[str, Any]:
        from .types import clean, now_iso
        from uuid import uuid4

        stored = {
            "id": clean(metric.get("id")) or f"metric_{uuid4().hex[:12]}",
            "name": clean(metric.get("name")) or "Engineering Metric",
            "category": clean(metric.get("category")) or "General",
            "value": number(metric.get("value"), 0),
            "unit": clean(metric.get("unit")),
            "artifactType": clean(metric.get("artifactType")),
            "artifactId": clean(metric.get("artifactId")),
            "createdAt": clean(metric.get("createdAt")) or now_iso(),
        }
        metrics.append(stored)
        return stored

    def aggregate(self, metrics: list[dict[str, Any]], observations: list[dict[str, Any]], approvals: list[dict[str, Any]]) -> dict[str, Any]:
        named = {metric["name"]: [] for metric in metrics}
        for metric in metrics:
            named.setdefault(metric["name"], []).append(number(metric.get("value"), 0))
        averages = {name: round(sum(values) / len(values), 2) for name, values in named.items() if values}
        success_observations = [item for item in observations if str(item.get("status")).lower() == "success"]
        failure_observations = [item for item in observations if str(item.get("status")).lower() not in {"success", "ok", "passed"}]
        approval_times = [number(item.get("approvalTimeMs"), 0) for item in approvals if number(item.get("approvalTimeMs"), 0) > 0]
        return {
            "planningTime": averages.get("Planning Time", 0),
            "executionTime": averages.get("Execution Time", 0),
            "qaTime": averages.get("QA Time", 0),
            "approvalTime": round(sum(approval_times) / len(approval_times), 2) if approval_times else averages.get("Approval Time", 0),
            "generationSuccess": self._ratio(success_observations, observations),
            "validationSuccess": averages.get("Validation Success", 0),
            "promptSuccess": averages.get("Prompt Success", 0),
            "repositoryUsage": averages.get("Repository Usage", 0),
            "memoryReuse": averages.get("Memory Reuse", 0),
            "averageReadiness": averages.get("Average Readiness", 0),
            "averageCoverage": averages.get("Average Coverage", 0),
            "averageRisk": averages.get("Average Risk", 0),
            "averageConfidence": averages.get("Average Confidence", 0),
            "failureCount": len(failure_observations),
            "metricCount": len(metrics),
        }

    def _ratio(self, numerator: list[Any], denominator: list[Any]) -> float:
        if not denominator:
            return 0
        return round((len(numerator) / len(denominator)) * 100, 2)
