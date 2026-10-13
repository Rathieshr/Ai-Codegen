"""Lifecycle action and transition rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .events import STATE_SEQUENCE, normalize_artifact_type


@dataclass(frozen=True)
class LifecycleRuleResult:
    allowed_actions: list[str]
    blocked_actions: list[dict[str, str]]
    next_action: str
    owner: str
    blocking_reason: str


OWNER_BY_STAGE = {
    "Planning": "Product Owner",
    "Execution": "Engineering",
    "Validation": "Engineering Reviewer",
    "QA": "QA",
    "Release": "Release Owner",
}

ACTION_TO_STATE = {
    "Analyze": "Analyzed",
    "Review": "Reviewed",
    "Approve": "Approved",
    "Generate Tasks": "Execution Ready",
    "Open Execution": "Execution Ready",
    "Build Execution Package": "Execution Package Built",
    "Generate Execution Plan": "Execution Plan Generated",
    "Start Implementation": "Implementation Started",
    "Complete Implementation": "Implementation Complete",
    "Validate Implementation": "Implementation Validated",
    "Open QA": "QA Analysis Complete",
    "Run QA Analysis": "QA Analysis Complete",
    "Generate Tests": "Tests Generated",
    "Verify Coverage": "Coverage Verified",
    "Complete Regression": "Regression Complete",
    "Recommend Release": "Release Ready",
    "Release": "Released",
    "Archive": "Archived",
}

NEXT_ACTION_BY_STATE = {
    "Draft": "Analyze",
    "Analyzed": "Review",
    "Reviewed": "Approve",
    "Approved": "Generate Tasks",
    "Execution Ready": "Build Execution Package",
    "Execution Package Built": "Generate Execution Plan",
    "Execution Plan Generated": "Start Implementation",
    "Implementation Started": "Complete Implementation",
    "Implementation Complete": "Validate Implementation",
    "Implementation Validated": "Open QA",
    "QA Analysis Complete": "Generate Tests",
    "Tests Generated": "Verify Coverage",
    "Coverage Verified": "Complete Regression",
    "Regression Complete": "Recommend Release",
    "Release Ready": "Release",
    "Released": "Archive",
    "Archived": "",
}


class LifecycleRules:
    def stage_for_state(self, state: str) -> str:
        if state in {"Draft", "Analyzed", "Reviewed", "Approved"}:
            return "Planning"
        if state in {"Execution Ready", "Execution Package Built", "Execution Plan Generated", "Implementation Started", "Implementation Complete"}:
            return "Execution"
        if state == "Implementation Validated":
            return "Validation"
        if state in {"QA Analysis Complete", "Tests Generated", "Coverage Verified", "Regression Complete"}:
            return "QA"
        return "Release"

    def progress_for_state(self, state: str) -> int:
        try:
            return int(round((STATE_SEQUENCE.index(state) / (len(STATE_SEQUENCE) - 1)) * 100))
        except ValueError:
            return 0

    def evaluate(self, artifact_type: str, state: str, context: dict[str, Any] | None = None) -> LifecycleRuleResult:
        artifact_type = normalize_artifact_type(artifact_type)
        context = context or {}
        next_action = self._next_action_for_artifact(artifact_type, state, context)
        blocked = self._blocked_actions(artifact_type, state, context)
        allowed = [] if not next_action else [next_action]
        allowed.extend(self._secondary_actions(artifact_type, state))
        blocked_names = {item["action"] for item in blocked}
        allowed = [action for action in allowed if action not in blocked_names]
        blocking_reason = blocked[0]["reason"] if next_action in blocked_names and blocked else ""
        return LifecycleRuleResult(
            allowed_actions=allowed,
            blocked_actions=blocked,
            next_action=allowed[0] if allowed else next_action,
            owner=OWNER_BY_STAGE[self.stage_for_state(state)],
            blocking_reason=blocking_reason,
        )

    def can_transition(self, from_state: str, to_state: str, context: dict[str, Any] | None = None) -> tuple[bool, str]:
        if from_state == to_state:
            return True, "No state change required."
        if from_state not in STATE_SEQUENCE or to_state not in STATE_SEQUENCE:
            return False, "Unknown lifecycle state."
        if to_state == "Archived":
            return True, "Archive is allowed."
        if STATE_SEQUENCE.index(to_state) == STATE_SEQUENCE.index(from_state) + 1:
            return True, "Sequential transition allowed."
        if STATE_SEQUENCE.index(to_state) < STATE_SEQUENCE.index(from_state):
            return False, "Use rollback for backwards lifecycle movement."
        return False, f"Cannot skip from {from_state} to {to_state}."

    def _next_action_for_artifact(self, artifact_type: str, state: str, context: dict[str, Any]) -> str:
        if artifact_type == "Story" and state == "Approved":
            return "Generate Tasks" if not context.get("has_tasks") else "Open Execution"
        if artifact_type == "Task" and state in {"Approved", "Execution Ready"}:
            return "Build Execution Package"
        if artifact_type == "Execution Package" and state in {"Approved", "Execution Ready", "Execution Package Built"}:
            return "Generate Execution Plan"
        if artifact_type == "Validation Report" and state == "Implementation Validated":
            return "Open QA"
        if artifact_type == "QA Report" and state in {"QA Analysis Complete", "Tests Generated", "Coverage Verified", "Regression Complete"}:
            return NEXT_ACTION_BY_STATE[state]
        return NEXT_ACTION_BY_STATE.get(state, "")

    def _secondary_actions(self, artifact_type: str, state: str) -> list[str]:
        actions = ["History", "Diagnostics"]
        if state not in {"Released", "Archived"}:
            actions.append("Rollback")
        if artifact_type in {"Epic", "Feature", "Story"} and state == "Approved":
            actions.append("Open Planning")
        if artifact_type in {"Story", "Task", "Execution Package"} and state in {"Approved", "Execution Ready", "Execution Package Built", "Execution Plan Generated"}:
            actions.append("Open Execution")
        if state in {"Implementation Validated", "QA Analysis Complete", "Tests Generated", "Coverage Verified", "Regression Complete", "Release Ready"}:
            actions.append("Open QA")
        return actions

    def _blocked_actions(self, artifact_type: str, state: str, context: dict[str, Any]) -> list[dict[str, str]]:
        blocked: list[dict[str, str]] = []
        if artifact_type == "Story" and context.get("has_unapproved_story"):
            blocked.append({"action": "Generate Tasks", "reason": "Story must be approved before Task generation."})
        if artifact_type == "Task" and state not in {"Approved", "Execution Ready"}:
            blocked.append({"action": "Build Execution Package", "reason": "Task must be approved before Execution Package generation."})
        if not context.get("has_execution_package") and state in {"Implementation Validated", "QA Analysis Complete"}:
            blocked.append({"action": "Run QA Analysis", "reason": "Execution Package is required before QA Intelligence."})
        if context.get("validation_status") in {"Failed", "Blocked"}:
            blocked.append({"action": "Open QA", "reason": "Implementation Validation must pass or be reviewed before QA."})
        if context.get("qa_status") == "Blocked":
            blocked.append({"action": "Release", "reason": "QA Readiness is Blocked."})
        return blocked
