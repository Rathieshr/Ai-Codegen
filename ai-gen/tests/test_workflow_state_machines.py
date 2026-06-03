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

    def test_ui_task_requires_ui_handoff_after_ui_plan_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 304, "type": "UI Task", "title": "Login screen"})
            self.assertEqual(pipeline["workflow_state"], "not_generated")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ui_plan")
            self.assertEqual(pipeline["workflow_state"], "ui_plan_ready")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ui_plan", approved_by="tester")
            self.assertEqual(pipeline["workflow_state"], "handoff_pending")
            self.assertEqual(pipeline["current_stage"], "ui_handoff")
            self.assertIn("generate_ui_handoff", pipeline["allowed_actions"]["workflow_actions"])
            self.assertNotIn("view_handoff", pipeline["allowed_actions"]["workflow_actions"])

    def test_ui_task_handoff_ready_summary_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 305, "type": "UI Task", "title": "Login screen"})
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ui_plan")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ui_plan", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ui_handoff")
            self.assertEqual(pipeline["workflow_state"], "handoff_ready")
            self.assertEqual(pipeline["workflow_summary"], "UI handoff is ready for approval.")
            self.assertIn("approve_plan", pipeline["allowed_actions"]["workflow_actions"])

    def test_story_delivery_starts_with_generate_story_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 306, "type": "User Story", "title": "Phone OTP login"})
            self.assertEqual(pipeline["workflow_state"], "not_generated")
            self.assertEqual(pipeline["workflow_summary"], "Generate a story plan.")
            self.assertIn("generate_story_plan", pipeline["allowed_actions"]["workflow_actions"])

    def test_story_delivery_with_unknowns_stays_in_clarification_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 307, "type": "User Story", "title": "Phone OTP login"})
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            self.assertEqual(pipeline["workflow_state"], "needs_clarification")
            self.assertEqual(pipeline["workflow_summary"], "Clarifications are required before approval.")
            self.assertIn("add_clarification", pipeline["allowed_actions"]["workflow_actions"])
            self.assertIn("regenerate_with_clarifications", pipeline["allowed_actions"]["workflow_actions"])

    def test_story_delivery_becomes_planned_after_regeneration_clears_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {"id": 308, "type": "User Story", "title": "Phone OTP login"},
                refinement={
                    "base_flows": ["login", "otp_verification"],
                    "variants": ["phone_otp"],
                    "surfaces": ["ui_screen"],
                    "fields": ["phone_number", "otp"],
                    "validations": ["auth_required"],
                },
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            pipeline = controller.add_stage_feedback(
                pipeline["pipeline_id"],
                "ba",
                "OTP expires in 120 seconds. Retry allowed 3 times. Second factor screen required.",
                "reviewer",
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            self.assertEqual(pipeline["workflow_state"], "planned")
            self.assertEqual(pipeline["workflow_summary"], "Story plan generated and awaiting approval.")
            self.assertIn("approve_story", pipeline["allowed_actions"]["workflow_actions"])

    def test_story_delivery_requires_ba_approval_before_task_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 309, "type": "User Story", "title": "Phone OTP login"})
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            self.assertEqual(pipeline["stages"]["task_planning"]["status"], "locked")

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
