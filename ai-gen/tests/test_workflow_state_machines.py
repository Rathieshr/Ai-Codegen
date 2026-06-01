from __future__ import annotations

import tempfile
import unittest

from backend.orchestrator.react_controller import PipelineController
from backend.workflow.action_visibility import get_allowed_actions


class WorkflowStateMachineTests(unittest.TestCase):
    def test_epic_state_transitions_to_approved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 301, "type": "Epic", "title": "Checkout modernization"})
            self.assertEqual(pipeline["workflow_state"], "not_generated")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "epic_analysis")
            self.assertEqual(pipeline["workflow_state"], "generated")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "epic_analysis", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "feature_generation")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "feature_generation", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "story_generation")
            self.assertEqual(pipeline["workflow_state"], "review")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "story_generation", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "review")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "review", approved_by="tester")
            self.assertEqual(pipeline["workflow_state"], "approved")
            self.assertEqual(pipeline["workflow_summary"], "Plan approved and ready for work item creation.")

    def test_task_summary_uses_packet_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 302, "type": "Task", "title": "Implement resend cooldown"})
            self.assertEqual(pipeline["workflow_summary"], "Generate an Execution Packet.")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "task_analysis")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "task_analysis", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "dev_packet")
            self.assertEqual(pipeline["workflow_state"], "packet_ready")
            self.assertEqual(pipeline["workflow_summary"], "Execution packet is ready.")

    def test_action_visibility_hides_create_when_no_drafts(self) -> None:
        self.assertEqual(
            get_allowed_actions("epic_planning", "approved", 0, None),
            [],
        )

    def test_action_visibility_task_shows_execution_actions(self) -> None:
        actions = get_allowed_actions("task_execution", "packet_ready", 0, "approved")
        self.assertIn("open_in_vscode", actions)
        self.assertIn("copy_execution_packet", actions)
        self.assertNotIn("approve_plan", actions)


if __name__ == "__main__":
    unittest.main()
