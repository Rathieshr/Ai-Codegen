"""Observability collection for intelligence engines and provider calls."""

from __future__ import annotations

from typing import Any

from .types import normalize_observation, number


class ObservabilityEngine:
    def record(self, observations: list[dict[str, Any]], observation: dict[str, Any]) -> dict[str, Any]:
        stored = normalize_observation(observation)
        observations.append(stored)
        return stored

    def summary(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        by_engine: dict[str, int] = {}
        by_status: dict[str, int] = {}
        durations: list[float] = []
        token_total = 0.0
        for item in observations:
            engine = str(item.get("engine") or "Unknown Engine")
            status = str(item.get("status") or "unknown")
            by_engine[engine] = by_engine.get(engine, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            durations.append(number(item.get("durationMs"), 0))
            usage = item.get("tokenUsage") if isinstance(item.get("tokenUsage"), dict) else {}
            token_total += number(usage.get("prompt_tokens") or usage.get("promptTokens"), 0)
            token_total += number(usage.get("completion_tokens") or usage.get("completionTokens"), 0)
        failures = sum(count for status, count in by_status.items() if status.lower() not in {"success", "ok", "passed"})
        return {
            "observations": observations,
            "count": len(observations),
            "byEngine": by_engine,
            "byStatus": by_status,
            "averageLatencyMs": round(sum(durations) / len(durations), 2) if durations else 0,
            "failureCount": failures,
            "tokenUsage": round(token_total, 2),
        }
