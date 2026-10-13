"""Tests for ai-gen comment parsing and effective work-item context."""

from __future__ import annotations

import tempfile
import unittest

from backend.context.ai_gen_comment_parser import filter_ai_gen_comments, parse_ai_gen_comment
from backend.context.work_item_context_builder import build_effective_work_item_context
from backend.orchestrator.react_controller import PipelineController
from backend.workflow.artifact_classifier import classify_work_item


class EffectiveWorkItemContextTests(unittest.TestCase):
    def test_parse_clarification_comment(self) -> None:
        parsed = parse_ai_gen_comment(
            "[ai-gen Clarification]\n"
            "Stage: BA\n"
            "Pipeline: pipeline_123\n"
            "Work Item: 77\n"
            "Author: azure_devops\n"
            "OTP expires in 2 minutes.\n"
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["type"], "clarification")
        self.assertEqual(parsed["stage"], "ba")
        self.assertEqual(parsed["pipeline_id"], "pipeline_123")
        self.assertEqual(parsed["work_item_id"], "77")
        self.assertEqual(parsed["author"], "azure_devops")
        self.assertIn("OTP expires", parsed["body"])

    def test_parse_approval_comment(self) -> None:
        parsed = parse_ai_gen_comment("[ai-gen Approval]\nStage: DEV\nApproved by ai-gen.")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["type"], "approval")
        self.assertEqual(parsed["stage"], "dev")

    def test_filter_ignores_unrelated_comments(self) -> None:
        filtered = filter_ai_gen_comments(
            [
                {"id": 1, "text": "plain user comment"},
                {"id": 2, "text": "[ai-gen Revision]\nStage: BA\nRetry policy is 3."},
            ]
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], 2)
        self.assertEqual(filtered[0]["type"], "revision")

    def test_effective_context_includes_clarifications_handoffs_and_feedback(self) -> None:
        effective = build_effective_work_item_context(
            {
                "id": 99,
                "type": "Story",
                "title": "Phone OTP login",
                "description": "Support phone number entry.",
                "acceptanceCriteria": "Phone number is required.",
                "tags": ["Android"],
            },
            pipeline_state={
                "stages": {
                    "ba": {
                        "review_feedback": [
                            {"comment": "Retry max is 3.", "timestamp": "2026-05-31T10:00:00+00:00"},
                        ],
                        "unresolved_findings": [
                            {"message": "Clarify resend cooldown.", "severity": "blocking", "status": "open"},
                        ],
                    }
                }
            },
            ai_gen_comments=[
                {"id": 1, "text": "[ai-gen Clarification]\nStage: BA\nOTP is required after phone entry.", "created_at": "2026-05-31T09:00:00+00:00"},
                {"id": 2, "text": "[ai-gen Clarification]\nStage: BA\nOTP expires in 120 seconds.", "created_at": "2026-05-31T11:00:00+00:00"},
            ],
            approved_handoffs=[
                {"handoff_id": "handoff_dev_1", "stage": "dev", "status": "approved", "summary": "Execution packet approved.", "approved_at": "2026-05-31T12:00:00+00:00"},
            ],
        )
        self.assertIn("ai_gen_comments", effective["context_sources"])
        self.assertIn("approved_handoffs", effective["context_sources"])
        self.assertIn("pipeline_feedback", effective["context_sources"])
        self.assertIn("OTP is required after phone entry.", effective["effective_text"])
        self.assertIn("Execution packet approved.", effective["effective_text"])
        self.assertLess(
            effective["effective_text"].find("Phone OTP login"),
            effective["effective_text"].rfind("OTP expires in 120 seconds."),
        )

    def test_classifier_can_use_effective_context_when_raw_description_is_weak(self) -> None:
        effective = {
            "effective_text": "QA regression suite refresh. Automation candidate coverage is needed.",
        }
        classification = classify_work_item(
            {"type": "Task", "title": "Refresh coverage", "description": ""},
            effective_context=effective,
        )
        self.assertEqual(classification["recommended_template"], "qa_task")

    def test_create_pipeline_stores_pipeline_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {"id": 101, "type": "Story", "title": "Phone OTP login", "description": "Support phone login."},
                ai_gen_comments=[
                    {"id": 1, "text": "[ai-gen Clarification]\nStage: BA\nOTP is required after phone entry."},
                ],
            )
            self.assertIn("pipeline_context", pipeline)
            self.assertEqual(pipeline["pipeline_context"]["comment_count"], 1)
            self.assertIn("ai_gen_comments", pipeline["pipeline_context"]["context_sources"])

    def test_regeneration_uses_comments_not_raw_description_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 102,
                    "type": "Story",
                    "title": "Phone OTP login",
                    "description": "Focus first on phone number input.",
                    "acceptanceCriteria": "",
                },
                refinement={"base_flows": ["login"], "variants": ["phone_otp"]},
                ai_gen_comments=[
                    {"id": 1, "text": "[ai-gen Clarification]\nStage: BA\nOTP is required after phone entry.\nRetry max is 3."},
                ],
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            self.assertNotIn(
                "Is OTP or a second-factor step required after the primary input succeeds?",
                pipeline["stages"]["ba"]["output"]["unknowns"],
            )


if __name__ == "__main__":
    unittest.main()
