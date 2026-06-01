from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class QaTaskStateMachine(BaseWorkflowStateMachine):
    workflow_template = "qa_task"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Design tests for the QA task.",
        "test_plan_ready": "Test plan is ready.",
        "approved": "Test plan approved.",
    }

    def derive_state(self) -> str:
        if self.stage_is_approved("test_design") or self.stage_is_approved("automation_draft_optional"):
            return "approved"
        if self.stage_has_output("test_design") or self.stage_has_output("automation_draft_optional"):
            return "test_plan_ready"
        return self.initial_state
