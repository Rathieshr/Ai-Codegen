from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class TaskStateMachine(BaseWorkflowStateMachine):
    workflow_template = "task_execution"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Generate an Execution Packet.",
        "packet_ready": "Execution packet is ready.",
        "validated": "Execution packet has been validated.",
    }

    def derive_state(self) -> str:
        if self.stage_has_output("test_checklist") or self.stage_is_approved("test_checklist"):
            return "validated"
        if self.stage_has_output("dev_packet") or self.stage_is_approved("dev_packet"):
            return "packet_ready"
        return self.initial_state
