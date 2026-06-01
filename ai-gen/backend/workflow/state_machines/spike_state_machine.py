from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class SpikeStateMachine(BaseWorkflowStateMachine):
    workflow_template = "spike"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Start the research plan.",
        "research_ready": "Research plan and findings are ready.",
        "completed": "Spike recommendation completed.",
    }

    def derive_state(self) -> str:
        if self.stage_has_output("recommendation") or self.stage_is_approved("recommendation"):
            return "completed"
        if self.stage_has_output("research_plan") or self.stage_has_output("findings"):
            return "research_ready"
        return self.initial_state
