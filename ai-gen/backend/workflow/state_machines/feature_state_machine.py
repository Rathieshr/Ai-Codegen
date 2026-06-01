from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine


class FeatureStateMachine(BaseWorkflowStateMachine):
    workflow_template = "feature_planning"
    initial_state = "not_generated"
    state_summaries = {
        "not_generated": "Generate a Feature Breakdown.",
        "stories_generated": "Feature breakdown generated and awaiting review.",
        "review": "Feature plan is in review before approval.",
        "approved": "Plan approved and ready for work item creation.",
        "work_items_created": "Selected Azure DevOps work items were created.",
    }

    def derive_state(self) -> str:
        if self.any_created_drafts():
            return "work_items_created"
        if self.stage_is_approved("review"):
            return "approved"
        if self.stage_has_output("story_generation") or self.stage_status("review") in {"generated", "needs_revision"}:
            return "review"
        if self.stage_has_output("feature_analysis"):
            return "stories_generated"
        return self.initial_state
