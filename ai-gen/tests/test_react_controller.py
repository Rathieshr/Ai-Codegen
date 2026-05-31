"""Tests for the deterministic pipeline controller."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.orchestrator.react_controller import PipelineController


class ReactControllerTests(unittest.TestCase):
    def test_create_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 123, "title": "Add login screen"})
            self.assertEqual(pipeline["current_stage"], "ba")
            self.assertEqual(pipeline["stages"]["ba"]["status"], "pending")
            self.assertEqual(pipeline["version"], 1)
            self.assertIn("allowed_actions", pipeline)
            self.assertEqual(pipeline["allowed_actions"]["current_stage_actions"], ["generate"])

    def test_run_ba_approve_and_run_ui_creates_handoffs(self) -> None:
        with tempfile.TemporaryDirectory() as pipeline_root, tempfile.TemporaryDirectory() as handoff_root, patch.dict(
            os.environ,
            {"AI_GEN_HANDOFF_ROOT": handoff_root},
            clear=False,
        ):
            controller = PipelineController(pipeline_root)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Add a login screen with phone number",
                    "description": "User signs in with phone number.",
                    "acceptanceCriteria": "Phone number is required.",
                },
                refinement={
                    "base_flows": ["login", "otp_verification"],
                    "variants": ["phone_otp"],
                    "surfaces": ["ui_screen", "authentication"],
                    "fields": ["phone_number", "otp"],
                    "validations": ["required", "format"],
                },
            )

            original_version = pipeline["version"]
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            self.assertIn("assistant", pipeline["stages"]["ba"]["output"])
            draft_handoff_id = pipeline["stages"]["ba"]["handoff_id"]
            self.assertTrue(draft_handoff_id)
            self.assertGreater(pipeline["version"], original_version)
            self.assertIn("approve", pipeline["allowed_actions"]["current_stage_actions"])

            pipeline = controller.add_stage_feedback(
                pipeline["pipeline_id"],
                "ba",
                "retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
                "reviewer",
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            run_version = pipeline["version"]
            self.assertIn("approve", pipeline["allowed_actions"]["current_stage_actions"])
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ba", approved_by="tester")
            self.assertEqual(pipeline["stages"]["ui"]["status"], "pending")
            approved_handoff = controller.load_handoff(pipeline["stages"]["ba"]["handoff_id"])
            self.assertEqual(approved_handoff["status"], "approved")
            markdown_path = Path(handoff_root) / "work_items" / "123" / "ba_v1.md"
            self.assertTrue(markdown_path.exists())
            self.assertGreater(pipeline["version"], run_version)

            pipeline = controller.run_stage(pipeline["pipeline_id"], "ui")
            self.assertIn("screen_name", pipeline["stages"]["ui"]["output"])
            self.assertEqual(pipeline["refinement"]["variants"], ["phone_otp"])
            self.assertEqual(pipeline["current_stage_findings"], [])
            self.assertIn("approve", pipeline["allowed_actions"]["current_stage_actions"])

    def test_load_latest_pipeline_for_work_item_returns_newest_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            first = controller.create_pipeline({"id": 123, "title": "First"})
            second = controller.create_pipeline({"id": 123, "title": "Second"})
            latest = controller.get_pipeline_for_work_item("123")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["pipeline_id"], second["pipeline_id"])

    def test_feedback_is_stored_and_regenerate_uses_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Add login screen",
                    "description": "Use phone login.",
                    "acceptanceCriteria": "",
                },
                refinement={"base_flows": ["login"], "variants": ["phone_otp"]},
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            pipeline = controller.add_stage_feedback(pipeline["pipeline_id"], "ba", "Clarify that OTP is required after phone entry.", "reviewer")
            self.assertEqual(pipeline["stages"]["ba"]["review_feedback"][0]["comment"], "Clarify that OTP is required after phone entry.")

            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            self.assertIn("Review clarifications", pipeline["stages"]["ba"]["output"]["refined_requirement"])

    def test_regeneration_resolves_matching_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Clarify onboarding flow",
                    "description": "Support the new entry path.",
                    "acceptanceCriteria": "",
                },
                refinement={},
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            self.assertTrue(pipeline["stages"]["ba"]["unresolved_findings"])
            finding_types = {finding["type"] for finding in pipeline["stages"]["ba"]["unresolved_findings"]}
            self.assertIn("missing_acceptance_criteria", finding_types)
            pipeline = controller.add_stage_feedback(
                pipeline["pipeline_id"],
                "ba",
                "Acceptance criteria: User can start the entry flow and reach the expected success state.",
                "reviewer",
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            resolved_types = {finding["type"] for finding in pipeline["stages"]["ba"]["resolved_findings"]}
            self.assertIn("missing_acceptance_criteria", resolved_types)

    def test_ba_regeneration_clears_answered_otp_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Ai Gen Extension Test",
                    "description": "Focus first on phone number input and otp verification step.",
                    "acceptanceCriteria": "Phone number input is required.",
                },
                refinement={
                    "base_flows": ["login", "otp_verification"],
                    "variants": ["phone_otp"],
                    "fields": ["phone_number", "otp"],
                },
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            self.assertIn(
                "Is OTP or a second-factor step required after the primary input succeeds?",
                pipeline["stages"]["ba"]["output"]["unknowns"],
            )
            self.assertIn(
                "Clarify OTP retry and expiry policy.",
                pipeline["stages"]["ba"]["output"]["unknowns"],
            )

            pipeline = controller.add_stage_feedback(
                pipeline["pipeline_id"],
                "ba",
                "yes retry policy 3 times max. second factor needed after primary input succeeds. yes otp is needed",
                "reviewer",
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            self.assertNotIn(
                "Is OTP or a second-factor step required after the primary input succeeds?",
                pipeline["stages"]["ba"]["output"]["unknowns"],
            )
            self.assertNotIn(
                "Clarify OTP retry and expiry policy.",
                pipeline["stages"]["ba"]["output"]["unknowns"],
            )

    def test_ba_findings_do_not_leak_into_ui_stage_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Ai Gen Extension Test",
                    "description": "Focus first on phone number input and otp verification step.",
                    "acceptanceCriteria": "Phone number input is required.",
                },
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
                "retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
                "reviewer",
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ba", approved_by="tester")

            self.assertEqual(pipeline["stages"]["ba"]["unresolved_findings"], [])
            self.assertTrue(pipeline["stages"]["ba"]["resolved_findings"])

            pipeline = controller.run_stage(pipeline["pipeline_id"], "ui")
            self.assertEqual(pipeline["current_stage"], "ui")
            self.assertEqual(pipeline["current_stage_findings"], [])
            self.assertEqual(pipeline["current_stage_blocking_findings"], [])
            self.assertEqual(pipeline["stages"]["ui"]["output"].get("unknowns"), [])

    def test_resolved_ba_unknowns_do_not_reappear_in_dev_or_test_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Ai Gen Extension Test",
                    "description": "Focus first on phone number input and otp verification step.",
                    "acceptanceCriteria": "Phone number input is required.",
                },
                refinement={
                    "base_flows": ["login", "otp_verification"],
                    "variants": ["phone_otp"],
                    "surfaces": ["ui_screen"],
                    "fields": ["phone_number", "otp"],
                    "validations": ["auth_required"],
                    "refinement_unknowns": ["Clarify OTP retry and expiry policy."],
                },
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            pipeline = controller.add_stage_feedback(
                pipeline["pipeline_id"],
                "ba",
                "retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
                "reviewer",
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ba", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ui")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ui", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "dev")
            self.assertNotIn("Clarify OTP retry and expiry policy.", pipeline["stages"]["dev"]["output"]["execution_packet"])
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "dev", approved_by="tester")
            pipeline = controller.run_stage(pipeline["pipeline_id"], "test")
            self.assertEqual(pipeline["stages"]["test"]["output"].get("unknowns"), [])

    def test_warning_only_stage_keeps_approve_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Ai Gen Extension Test",
                    "description": "Focus first on phone number input and otp verification step.",
                    "acceptanceCriteria": "",
                },
                refinement={
                    "base_flows": ["login", "otp_verification"],
                    "variants": ["phone_otp"],
                    "surfaces": ["ui_screen"],
                    "fields": ["phone_number", "otp"],
                    "validations": ["auth_required"],
                },
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            actions = pipeline["allowed_actions"]["current_stage_actions"]
            self.assertNotIn("generate", actions)
            self.assertIn("approve", actions)
            self.assertIn("regenerate", actions)
            self.assertNotIn("add_clarification", actions)

    def test_approved_stage_keeps_only_handoff_visibility_in_stage_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 123, "title": "Add login screen"})
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ba", approved_by="tester")
            self.assertIn("ba", pipeline["allowed_actions"]["view_handoff_stages"])
            self.assertNotIn("ba", pipeline["allowed_actions"]["approve_stages"])
            self.assertNotIn("ba", pipeline["allowed_actions"]["regenerate_stages"])

    def test_all_findings_keeps_resolved_ba_audit_trail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline(
                {
                    "id": 123,
                    "title": "Clarify onboarding flow",
                    "description": "Support the new entry path.",
                    "acceptanceCriteria": "",
                },
                refinement={},
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            pipeline = controller.add_stage_feedback(
                pipeline["pipeline_id"],
                "ba",
                "Acceptance criteria: User can start the entry flow and reach the expected success state.",
                "reviewer",
            )
            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba", regenerate=True)
            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ba", approved_by="tester")
            resolved_ba = [
                finding for finding in pipeline["all_findings"]
                if finding.get("target_stage") == "ba" and finding.get("status") == "resolved"
            ]
            self.assertTrue(resolved_ba)
            self.assertTrue(pipeline["resolved_findings"])


if __name__ == "__main__":
    unittest.main()
