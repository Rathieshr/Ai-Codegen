from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class StoryStateMachine(BaseWorkflowStateMachine):
    workflow_template = "story_delivery"
    initial_state = "needs_clarification"
    state_summaries = {
        "needs_clarification": "Clarify the story before approval.",
        "planned": "Story plan generated and awaiting approval.",
        "approved": "Story approved and ready for downstream planning.",
        "tasks_generated": "Child tasks and test plan were generated.",
    }

    def derive_state(self) -> str:
        if self.stage_has_output("task_planning") or self.stage_has_output("test_planning"):
            return "tasks_generated"
        if self.stage_is_approved("ba") and (self.stage_is_approved("ui_optional") or self.stage_status("ui_optional") == "skipped" or self.stage_status("ui_optional") == "locked"):
            return "approved"
        if self.stage_has_output("ba") or self.stage_has_output("ui_optional"):
            return "planned"
        return self.initial_state
