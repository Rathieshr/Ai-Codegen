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

            run_version = pipeline["version"]
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

    def test_load_latest_pipeline_for_work_item_returns_newest_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            first = controller.create_pipeline({"id": 123, "title": "First"})
            second = controller.create_pipeline({"id": 123, "title": "Second"})
            latest = controller.get_pipeline_for_work_item("123")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["pipeline_id"], second["pipeline_id"])


if __name__ == "__main__":
    unittest.main()
