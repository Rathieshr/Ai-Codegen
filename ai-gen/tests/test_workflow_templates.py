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
            self.assertEqual(pipeline["stage_order"], ["epic_analysis", "story_generation", "review"])


if __name__ == "__main__":
    unittest.main()
