from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class StoryStateMachine(BaseWorkflowStateMachine):
    workflow_template = "story_delivery"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Generate a story plan.",
        "needs_clarification": "Clarifications are required before approval.",
        "planned": "Story plan generated and awaiting approval.",
        "approved": "Story approved and ready for downstream planning.",
        "tasks_generated": "Child tasks and test plan were generated.",
    }

    def derive_state(self) -> str:
        ba_stage = self.stage("ba")
        ui_stage = self.stage("ui_optional")
        ba_unknowns = list((ba_stage.get("output") or {}).get("unknowns") or [])
        ui_unknowns = list((ui_stage.get("output") or {}).get("unknowns") or [])
        if self.stage_has_output("task_planning") or self.stage_has_output("test_planning"):
            return "tasks_generated"
        if self.stage_is_approved("ba") and (self.stage_is_approved("ui_optional") or self.stage_status("ui_optional") == "skipped" or self.stage_status("ui_optional") == "locked"):
            return "approved"
        if (
            self.stage_status("ba") == "needs_revision"
            or self.stage_status("ui_optional") == "needs_revision"
            or ba_unknowns
            or ui_unknowns
        ):
            return "needs_clarification"
        if self.stage_has_output("ba") or self.stage_has_output("ui_optional"):
            return "planned"
        return self.initial_state
