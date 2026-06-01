from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class BugStateMachine(BaseWorkflowStateMachine):
    workflow_template = "bug_fix"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Analyze the bug.",
        "impact_analyzed": "Impact analysis completed.",
        "fix_ready": "Fix packet generated.",
        "validated": "Regression validation is ready.",
    }

    def derive_state(self) -> str:
        if self.stage_has_output("regression_tests") or self.stage_is_approved("regression_tests"):
            return "validated"
        if self.stage_has_output("fix_packet") or self.stage_is_approved("fix_packet"):
            return "fix_ready"
        if self.stage_has_output("impact_analysis") or self.stage_is_approved("impact_analysis"):
            return "impact_analyzed"
        return self.initial_state
