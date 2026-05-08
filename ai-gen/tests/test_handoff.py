"""Tests for handoff building, rendering, and storage."""

import os
import tempfile
import unittest

from backend.handoff.handoff_builder import build_handoff
from backend.handoff.markdown_renderer import render_handoff_markdown
from backend.handoff.storage import latest_handoff, list_handoffs, load_handoff, save_handoff
from backend.orchestrator.pipeline_state import create_initial_pipeline_state


class HandoffTests(unittest.TestCase):
    def test_handoff_builder_includes_stage_refinement_and_constraints(self) -> None:
        pipeline = create_initial_pipeline_state("pipeline_1", "azure_devops", "123", {"id": 123, "title": "Login"})
        pipeline.stages["dev"].version = 1
        stage_output = {
            "assistant": "dev",
            "task_summary": "Fix login validation",
            "constraints": ["Do not bypass credential validation."],
            "unknowns": ["Is OTP required?"],
        }
        handoff = build_handoff(
            pipeline_state=pipeline,
            stage="dev",
            stage_output=stage_output,
            refinement={"refined_variant": "phone_number"},
            repo_context={"resolved_repo_id": "repo_1"},
            status="draft",
        )
        self.assertEqual(handoff["stage"], "dev")
        self.assertEqual(handoff["constraints"], ["Do not bypass credential validation."])
        self.assertEqual(handoff["refinement"]["refined_variant"], "phone_number")

    def test_markdown_renderer_works(self) -> None:
        markdown = render_handoff_markdown(
            {
                "stage": "dev",
                "status": "draft",
                "summary": "Fix login validation",
                "content": {"task_summary": "Fix login validation"},
                "constraints": ["Do not bypass credential validation."],
                "open_questions": ["Is OTP required?"],
                "next_actions": ["Approve before testing."],
                "refinement": {"refined_variant": "phone_number"},
                "repo_context": {"resolved_repo_id": "repo_1"},
            }
        )
        self.assertIn("# DEV Handoff", markdown)
        self.assertIn("## Constraints", markdown)
        self.assertIn("## Open Questions", markdown)

    def test_save_load_and_latest_handoff_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, unittest.mock.patch.dict(os.environ, {"AI_GEN_HANDOFF_ROOT": temp_dir}, clear=False):
            handoff = {
                "handoff_id": "123:dev:v1",
                "pipeline_id": "pipeline_1",
                "work_item_id": "123",
                "stage": "dev",
                "version": 1,
                "status": "approved",
                "created_at": "now",
                "approved_at": "now",
                "source_stage": "dev",
                "target_stages": ["test"],
                "summary": "Fix login validation",
                "content": {"task_summary": "Fix login validation"},
                "refinement": {},
                "repo_context": {},
                "constraints": [],
                "open_questions": [],
                "next_actions": [],
            }
            save_handoff(handoff)
            self.assertEqual(load_handoff("123:dev:v1")["summary"], "Fix login validation")
            self.assertEqual(latest_handoff("123", "dev", status="approved")["handoff_id"], "123:dev:v1")
            self.assertEqual(len(list_handoffs("123")), 1)


if __name__ == "__main__":
    unittest.main()
