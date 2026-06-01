from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class EpicStateMachine(BaseWorkflowStateMachine):
    workflow_template = "epic_planning"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Generate an Epic Plan.",
        "generated": "Epic plan generated and awaiting review.",
        "review": "Epic plan is in review before approval.",
        "approved": "Plan approved and ready for work item creation.",
        "work_items_created": "Selected Azure DevOps work items were created.",
    }

    def derive_state(self) -> str:
        if self.any_created_drafts():
            return "work_items_created"
        if self.stage_is_approved("review"):
            return "approved"
        if self.stage_has_output("story_generation") or self.stage_has_output("review") or self.stage_status("review") in {"generated", "needs_revision"}:
            return "review"
        if self.stage_has_output("epic_analysis") or self.stage_has_output("feature_generation"):
            return "generated"
        return self.initial_state
