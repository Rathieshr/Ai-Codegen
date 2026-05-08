"""Tests for the deterministic pipeline controller."""

import os
import tempfile
import unittest
from unittest.mock import patch

from backend.orchestrator.react_controller import PipelineController


class ReactControllerTests(unittest.TestCase):
    def test_create_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = PipelineController(temp_dir)
            pipeline = controller.create_pipeline({"id": 123, "title": "Add login screen"})
            self.assertEqual(pipeline["current_stage"], "ba")
            self.assertEqual(pipeline["stages"]["ba"]["status"], "pending")

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
                    "refined_base_flow": "login",
                    "refined_variant": "phone_number",
                    "refined_surface": "ui_screen",
                    "refined_fields": ["phone_number"],
                    "refined_validations": ["required", "phone_format"],
                },
            )

            pipeline = controller.run_stage(pipeline["pipeline_id"], "ba")
            self.assertIn("assistant", pipeline["stages"]["ba"]["output"])
            draft_handoff_id = pipeline["stages"]["ba"]["handoff_id"]
            self.assertTrue(draft_handoff_id)

            pipeline = controller.approve_stage(pipeline["pipeline_id"], "ba", approved_by="tester")
            self.assertEqual(pipeline["stages"]["ui"]["status"], "pending")
            approved_handoff = controller.load_handoff(pipeline["stages"]["ba"]["handoff_id"])
            self.assertEqual(approved_handoff["status"], "approved")

            pipeline = controller.run_stage(pipeline["pipeline_id"], "ui")
            self.assertIn("screen_name", pipeline["stages"]["ui"]["output"])


if __name__ == "__main__":
    unittest.main()
