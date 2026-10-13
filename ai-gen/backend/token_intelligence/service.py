"""Persistence and platform events for immutable BudgetedPrompt artifacts."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore

from .engine import TokenBudgetEngine


class TokenIntelligenceService:
    def __init__(self, store: JsonMapStore, *, engine: TokenBudgetEngine | None = None, platform: Any | None = None) -> None:
        self.store = store
        self.engine = engine or TokenBudgetEngine()
        self.platform = platform

    def optimize(
        self,
        compiled_prompt: dict[str, Any],
        *,
        budget_tokens: int,
        reserved_output_tokens: int | None = None,
        actual_tokens: int | None = None,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        self._event("TokenOptimizationRequested", correlation_id, {"compiledPromptId": compiled_prompt.get("compiledPromptId"), "budgetTokens": budget_tokens})
        result = self.engine.optimize(
            compiled_prompt,
            budget_tokens=budget_tokens,
            reserved_output_tokens=reserved_output_tokens,
            actual_tokens=actual_tokens,
        )
        values = self.store.read()
        existing = values.get(result["budgetedPromptId"])
        if existing:
            if existing.get("immutableHash") != result.get("immutableHash"):
                raise ValueError("Budgeted Prompt identity collision detected.")
            self._event("BudgetedPromptReused", correlation_id, {"budgetedPromptId": result["budgetedPromptId"]})
            return deepcopy(existing)
        result["diagnostics"]["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        values[result["budgetedPromptId"]] = result
        self.store.write(values)
        event = "TokenOptimizationCompleted" if result["status"] == "Ready" else "TokenOptimizationBlocked"
        self._event(event, correlation_id, {"budgetedPromptId": result["budgetedPromptId"], "status": result["status"]})
        return deepcopy(result)

    def get(self, budgeted_prompt_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(budgeted_prompt_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def _event(self, event_type: str, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "API", "correlationId": correlation_id, "payload": payload})
