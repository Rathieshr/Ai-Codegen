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
            self.assertEqual(pipeline["workflow_state"], "review_ready")
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

    def test_epic_approve_hidden_until_review_ready_with_drafts(self) -> None:
        self.assertNotIn("approve_plan", get_allowed_actions("epic_planning", "generated", 0, None))
        self.assertIn("approve_plan", get_allowed_actions("epic_planning", "review_ready", 4, None))

    def test_epic_resume_action_shows_when_generated_without_drafts(self) -> None:
        self.assertEqual(get_allowed_actions("epic_planning", "generated", 0, None), ["resume_epic_plan"])

    def test_action_visibility_task_shows_execution_actions(self) -> None:
        actions = get_allowed_actions("task_execution", "packet_ready", 0, "approved")
        self.assertIn("open_in_vscode", actions)
        self.assertIn("copy_execution_packet", actions)
        self.assertNotIn("approve_plan", actions)

    def test_run_epic_plan_runs_internal_stages_and_creates_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 303, "type": "Epic", "title": "Identity modernization"})
            pipeline = controller.run_epic_plan(pipeline["pipeline_id"])
            self.assertTrue(pipeline["stages"]["epic_analysis"]["approved"])
            self.assertTrue(pipeline["stages"]["feature_generation"]["approved"])
            self.assertTrue(pipeline["stages"]["story_generation"]["approved"])
            self.assertTrue(pipeline["stages"]["review"]["output"])
            self.assertEqual(pipeline["workflow_state"], "review_ready")
            self.assertTrue(pipeline["draft_work_items"])
            self.assertNotEqual(pipeline["stages"]["feature_generation"]["status"], "locked")
            self.assertIn("approve_plan", pipeline["allowed_actions"]["workflow_actions"])


if __name__ == "__main__":
    unittest.main()
