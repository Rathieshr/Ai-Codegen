from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class UiTaskStateMachine(BaseWorkflowStateMachine):
    workflow_template = "ui_task"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Generate a UI plan.",
        "ui_plan_ready": "UI plan is ready for approval.",
        "handoff_pending": "UI plan approved. Generate the UI handoff.",
        "handoff_ready": "UI handoff is ready for approval.",
        "approved": "UI handoff approved.",
    }

    def derive_state(self) -> str:
        if self.stage_is_approved("ui_handoff"):
            return "approved"
        if self.stage_has_output("ui_handoff"):
            return "handoff_ready"
        if self.stage_is_approved("ui_plan"):
            return "handoff_pending"
        if self.stage_has_output("ui_plan"):
            return "ui_plan_ready"
        return self.initial_state
