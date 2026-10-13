"""Tests for workflow template routing and dynamic pipeline creation."""

from __future__ import annotations

import tempfile
import unittest

from backend.orchestrator.react_controller import PipelineController
from backend.workflow.artifact_classifier import classify_work_item


class WorkflowTemplateTests(unittest.TestCase):
    def test_bug_selects_bug_fix_template(self) -> None:
        classification = classify_work_item({"type": "Bug", "title": "Fix login crash"})
        self.assertEqual(classification["recommended_template"], "bug_fix")

    def test_task_selects_task_execution_template(self) -> None:
        classification = classify_work_item({"type": "Task", "title": "Update session timeout"})
        self.assertEqual(classification["recommended_template"], "task_execution")

    def test_story_selects_story_delivery_template(self) -> None:
        classification = classify_work_item({"type": "User Story", "title": "Add phone login"})
        self.assertEqual(classification["recommended_template"], "story_delivery")

    def test_epic_selects_epic_planning_template(self) -> None:
        classification = classify_work_item({"type": "Epic", "title": "Modernize checkout"})
        self.assertEqual(classification["recommended_template"], "epic_planning")

    def test_qa_task_selects_qa_task_template(self) -> None:
        classification = classify_work_item({"type": "QA Task", "title": "Regression suite refresh"})
        self.assertEqual(classification["recommended_template"], "qa_task")

    def test_ui_task_selects_ui_task_template(self) -> None:
        classification = classify_work_item(
            {"type": "Task", "title": "Refresh login screen layout"},
            refinement={"refined_surfaces": ["ui_screen"]},
        )
        self.assertEqual(classification["recommended_template"], "ui_task")

    def test_pipeline_contains_only_bug_fix_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 101, "type": "Bug", "title": "Fix OTP validation bug"})
            self.assertEqual(pipeline["workflow_template"], "bug_fix")
            self.assertEqual(pipeline["stage_order"], ["bug_analysis", "impact_analysis", "fix_packet", "regression_tests"])
            self.assertNotIn("ba", pipeline["stages"])
            self.assertNotIn("ui", pipeline["stages"])

    def test_pipeline_contains_only_task_execution_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 102, "type": "Task", "title": "Implement OTP resend cooldown"})
            self.assertEqual(pipeline["workflow_template"], "task_execution")
            self.assertEqual(pipeline["stage_order"], ["task_analysis", "dev_packet", "test_checklist"])

    def test_story_pipeline_contains_planning_and_child_task_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 103, "type": "Story", "title": "Phone OTP login"})
            self.assertEqual(pipeline["workflow_template"], "story_delivery")
            self.assertEqual(pipeline["stage_order"], ["ba", "ui_optional", "task_planning", "test_planning", "critic"])

    def test_epic_pipeline_contains_planning_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 104, "type": "Epic", "title": "Identity modernization"})
            self.assertEqual(pipeline["workflow_template"], "epic_planning")
            self.assertEqual(pipeline["stage_order"], ["epic_analysis", "feature_generation", "story_generation", "review"])

    def test_epic_story_generation_outputs_proposed_work_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 105, "type": "Epic", "title": "Identity modernization"})
            pipeline = controller.run_stage(pipeline["pipeline_id"], "epic_analysis")
            self.assertIn(pipeline["stages"]["epic_analysis"]["output"]["provider_used"], {"azure_phi", "domain_fallback", "deterministic_fallback"})
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "epic_analysis", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "feature_generation")
            self.assertIn(pipeline["stages"]["feature_generation"]["output"]["provider_used"], {"azure_phi", "domain_fallback", "deterministic_fallback"})
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "feature_generation", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "story_generation")
            output = pipeline["stages"]["story_generation"]["output"]
            self.assertIn(output["provider_used"], {"azure_phi", "domain_fallback", "deterministic_fallback"})
            self.assertTrue(output["proposed_work_items"])
            self.assertTrue(output["generated_work_items"])
            self.assertEqual(output["generated_work_items"][0]["draft_type"], "Feature")
            self.assertTrue(output["generated_work_items"][0]["children"])
            self.assertNotIn("proposed_stories", output)
            self.assertEqual(output["assistant"], "story_generator")

    def test_story_task_planning_outputs_child_work_item_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {"id": 106, "type": "Story", "title": "Phone OTP login"},
                refinement={
                    "base_flows": ["login", "otp_verification"],
                    "variants": ["phone_otp"],
                    "surfaces": ["ui_screen"],
                    "fields": ["phone_number", "otp"],
                },
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ba", approved_by="tester")
            pipeline = controller.skip_stage(pipeline["pipeline_id"], "ui_optional", "Use direct task planning for this test")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "task_planning")
            output = pipeline["stages"]["task_planning"]["output"]
            self.assertTrue(output["proposed_work_items"])
            self.assertTrue(output["generated_work_items"])
            self.assertEqual(output["proposed_work_items"][0]["source_stage"], "task_planning")
            self.assertIn(output["generated_work_items"][0]["draft_type"], {"Task"})
            self.assertNotIn("Review clarifications:", output["generated_work_items"][0]["title"])
            self.assertTrue(
                output["generated_work_items"][0]["title"].startswith("UI Task:")
                or output["generated_work_items"][0]["title"].startswith("Dev Task:")
            )
            self.assertIsNone(output["generated_work_items"][0]["azure_work_item_id"])

    def test_create_request_payload_and_created_mapping_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 107, "type": "Epic", "title": "Identity modernization"})
            pipeline = controller.run_stage(pipeline["pipeline_id"], "epic_analysis")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "epic_analysis", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "feature_generation")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "feature_generation", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "story_generation")
            drafts = controller.get_draft_work_items(pipeline["pipeline_id"])["draft_work_items"]
            draft_ids = [drafts[0]["draft_id"]]
            payload = controller.create_draft_work_items(pipeline["pipeline_id"], draft_ids, create_child_tasks=True)
            self.assertTrue(payload["work_item_create_requests"])
            created = controller.mark_draft_work_items_created(
                pipeline["pipeline_id"],
                [{"draft_id": payload["work_item_create_requests"][0]["draft_id"], "azure_work_item_id": 9001, "status": "created"}],
            )
            self.assertTrue(any(item["azure_work_item_id"] == 9001 for item in created["draft_work_items"]))

    def test_creation_result_is_stored_in_pipeline_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 108, "type": "Feature", "title": "Checkout improvements"})
            pipeline = controller.run_stage(pipeline["pipeline_id"], "feature_analysis")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "feature_analysis", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "story_generation")
            drafts = controller.get_draft_work_items(pipeline["pipeline_id"])["draft_work_items"]
            draft_id = drafts[0]["draft_id"]
            controller.mark_draft_work_items_created(
                pipeline["pipeline_id"],
                [{"draft_id": draft_id, "azure_work_item_id": 9010, "status": "created", "title": drafts[0]["title"], "type": drafts[0]["draft_type"]}],
            )
            stored = controller.get_pipeline(pipeline["pipeline_id"])
            self.assertTrue(stored["activity"])
            self.assertEqual(stored["activity"][-1]["type"], "work_item_creation_result")


if __name__ == "__main__":
    unittest.main()
