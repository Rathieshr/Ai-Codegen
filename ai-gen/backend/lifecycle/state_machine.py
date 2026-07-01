"""State machine for engineering lifecycle transitions."""

from __future__ import annotations

from typing import Any

from .events import normalize_state
from .rules import LifecycleRules


class LifecycleStateMachine:
    def __init__(self) -> None:
        self.rules = LifecycleRules()

    def transition(self, current_state: str, target_state: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        current = normalize_state(current_state)
        target = normalize_state(target_state)
        allowed, reason = self.rules.can_transition(current, target, context or {})
        return {
            "allowed": allowed,
            "fromState": current,
            "toState": target if allowed else current,
            "requestedState": target,
            "reason": reason,
        }

    def rollback(self, current_state: str) -> dict[str, Any]:
        current = normalize_state(current_state)
        sequence = [
            "Draft",
            "Analyzed",
            "Reviewed",
            "Approved",
            "Execution Ready",
            "Execution Package Built",
            "Execution Plan Generated",
            "Implementation Started",
            "Implementation Complete",
            "Implementation Validated",
            "QA Analysis Complete",
            "Tests Generated",
            "Coverage Verified",
            "Regression Complete",
            "Release Ready",
            "Released",
            "Archived",
        ]
        index = sequence.index(current) if current in sequence else 0
        target = sequence[max(0, index - 1)]
        return {
            "allowed": current != target,
            "fromState": current,
            "toState": target,
            "requestedState": target,
            "reason": "Rolled back to previous lifecycle state." if current != target else "Already at initial lifecycle state.",
        }
