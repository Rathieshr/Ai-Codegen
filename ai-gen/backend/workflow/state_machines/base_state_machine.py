"""Workflow-specific state machine helpers for Azure DevOps workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowSnapshot:
    workflow_template: str
    stages: dict[str, dict[str, Any]]
    draft_work_items: list[dict[str, Any]]


class BaseWorkflowStateMachine:
    workflow_template = "legacy_delivery"
    initial_state = "not_generated"
    state_labels: dict[str, str] = {}
    state_summaries: dict[str, str] = {}

    def __init__(self, snapshot: WorkflowSnapshot) -> None:
        self.snapshot = snapshot

    def derive_state(self) -> str:
        return self.initial_state

    def summary_for(self, state: str) -> str:
        return self.state_summaries.get(state, self.state_summaries.get(self.initial_state, "Review the current workflow state."))

    def label_for(self, state: str) -> str:
        return self.state_labels.get(state, state.replace("_", " "))

    def stage(self, name: str) -> dict[str, Any]:
        return dict(self.snapshot.stages.get(name) or {})

    def stage_has_output(self, name: str) -> bool:
        stage = self.stage(name)
        return bool(stage.get("output"))

    def stage_is_approved(self, name: str) -> bool:
        return bool(self.stage(name).get("approved"))

    def stage_status(self, name: str) -> str:
        return str(self.stage(name).get("status", "locked"))

    def any_created_drafts(self) -> bool:
        return any(str(item.get("status", "")) == "created" for item in self._flatten_drafts(self.snapshot.draft_work_items))

    def draft_count(self) -> int:
        return len(self._flatten_drafts(self.snapshot.draft_work_items))

    def _flatten_drafts(self, drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for draft in drafts:
            item = dict(draft)
            items.append(item)
            children = item.get("children") or item.get("child_drafts") or []
            items.extend(self._flatten_drafts([child for child in children if isinstance(child, dict)]))
        return items
