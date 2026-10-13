"""Purpose-aware token budget allocation without partial candidate truncation."""

from __future__ import annotations

from typing import Protocol

from .models import ContextCandidate, ContextRequest, ContextSourceType


DEVELOPER_PROMPT_ALLOCATIONS = {
    "Planning": 0.25, "Repository": 0.35, "EngineeringStandards": 0.10,
    "EngineeringMemory": 0.10, "ValidationHistory": 0.10, "LocalWorkspace": 0.10,
}


class IContextBudgetManager(Protocol):
    version: str
    def apply(self, request: ContextRequest, candidates: list[ContextCandidate]) -> tuple[list[ContextCandidate], list[dict], dict]: ...


class ContextBudgetManager:
    version = "purpose-allocation-v1"

    def __init__(self, allocations: dict[str, dict[str, float]] | None = None, system_reserve: int = 300, output_reserve: int = 500) -> None:
        self.allocations = allocations or {"DeveloperPrompt": DEVELOPER_PROMPT_ALLOCATIONS}
        self.system_reserve = system_reserve
        self.output_reserve = output_reserve

    def apply(self, request: ContextRequest, candidates: list[ContextCandidate]) -> tuple[list[ContextCandidate], list[dict], dict]:
        maximum = max(1, int(request.options.get("maxTokens", 4000) or 4000))
        requested_reserve = int(request.options.get("reservedTokens", self.system_reserve + self.output_reserve) or 0)
        # Keep small-model requests viable while still reserving half the window.
        reserved = min(maximum // 2, max(0, requested_reserve))
        available = maximum - reserved
        allocations = self.allocations.get(request.purpose, {})
        selected: list[ContextCandidate] = []
        omitted: list[dict] = []
        remaining = available
        source_used: dict[str, int] = {}
        # The manager is independently safe even when a caller bypasses ranking.
        ranked = sorted(candidates, key=lambda item: (-item.final_score, item.candidate_id))
        for candidate in ranked:
            source = candidate.source_type.value
            source_cap = int(available * allocations[source]) if source in allocations else available
            if candidate.token_estimate <= remaining and source_used.get(source, 0) + candidate.token_estimate <= source_cap:
                selected.append(candidate)
                remaining -= candidate.token_estimate
                source_used[source] = source_used.get(source, 0) + candidate.token_estimate
            else:
                omitted.append({"candidate": candidate, "reason": "token_budget_omitted"})
        selected_tokens = sum(item.token_estimate for item in selected)
        return selected, omitted, {
            "maximum": maximum, "reserved": reserved, "selected": selected_tokens,
            "omitted": sum(item["candidate"].token_estimate for item in omitted),
            "available": available, "sourceAllocation": allocations,
        }
