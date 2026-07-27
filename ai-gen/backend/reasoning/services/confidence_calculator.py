"""Confidence scoring grounded in provider output and EngineeringContext."""

from __future__ import annotations

from typing import Any


class ConfidenceCalculator:
    def calculate(
        self,
        response: dict[str, Any],
        context: dict[str, Any],
        evidence_catalog: list[dict[str, Any]],
    ) -> dict[str, Any]:
        provider = _score(response.get("confidence"))
        evidence_count = len(response.get("evidence") or [])
        evidence_coverage = min(100, round((evidence_count / max(1, min(len(evidence_catalog), 5))) * 100))
        repository = _score((context.get("repository") or {}).get("confidence"))
        similarity = _similarity(context)
        planning = _planning_certainty(context)
        overall = round(
            provider * 0.25
            + evidence_coverage * 0.25
            + repository * 0.20
            + similarity * 0.10
            + planning * 0.20
        )
        return {
            "overall": overall,
            "level": "High" if overall >= 80 else "Medium" if overall >= 55 else "Low",
            "providerConfidence": provider,
            "evidenceCoverage": evidence_coverage,
            "repositoryRelevance": repository,
            "similarityScore": similarity,
            "planningCertainty": planning,
        }


def _score(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("overall") or value.get("score") or value.get("value")
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 50
    if 0 <= score <= 1:
        score *= 100
    return max(0, min(100, round(score)))


def _similarity(context: dict[str, Any]) -> int:
    values = []
    for item in (context.get("similarWork") or {}).get("matches") or []:
        if isinstance(item, dict):
            values.append(_score(item.get("confidence") or item.get("similarity")))
    return max(values, default=50)


def _planning_certainty(context: dict[str, Any]) -> int:
    readiness = context.get("readiness") or {}
    explicit = readiness.get("score") or readiness.get("confidence")
    if explicit is not None:
        return _score(explicit)
    status = str(readiness.get("status") or (context.get("summary") or {}).get("readiness") or "")
    key = status.casefold().replace(" ", "")
    if "blocked" in key:
        return 20
    if "needs" in key:
        return 45
    if "recommend" in key:
        return 70
    if "ready" in key:
        return 90
    return 50
