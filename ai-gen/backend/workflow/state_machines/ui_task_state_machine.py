from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class UiTaskStateMachine(BaseWorkflowStateMachine):
    workflow_template = "ui_task"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Generate a UI plan.",
        "ui_plan_ready": "UI plan is ready.",
        "approved": "UI handoff approved.",
    }

    def derive_state(self) -> str:
        if self.stage_is_approved("ui_handoff") or self.stage_is_approved("ui_plan"):
            return "approved"
        if self.stage_has_output("ui_plan") or self.stage_has_output("ui_handoff"):
            return "ui_plan_ready"
        return self.initial_state
