"""Tests for pipeline stage state and approval rules."""

import unittest

from backend.orchestrator.approval_gate import approve_stage, can_run_stage, skip_stage
from backend.orchestrator.pipeline_state import create_initial_pipeline_state


class PipelineStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = create_initial_pipeline_state(
            pipeline_id="pipeline_123",
            source="azure_devops",
            work_item_id="123",
            work_item={"id": 123, "title": "Add login screen"},
        )

    def test_initial_state_locks_stages_correctly(self) -> None:
        self.assertEqual(self.pipeline.stages["ba"].status, "pending")
        self.assertEqual(self.pipeline.stages["ui"].status, "locked")
        self.assertEqual(self.pipeline.stages["dev"].status, "locked")

    def test_approving_ba_unlocks_ui(self) -> None:
        self.pipeline.stages["ba"].output = {"assistant": "ba", "refined_requirement": "Add login screen."}
        original_version = self.pipeline.version
        updated = approve_stage(self.pipeline, "ba")
        self.assertEqual(updated.stages["ba"].status, "approved")
        self.assertEqual(updated.stages["ui"].status, "pending")
        self.assertGreaterEqual(updated.stages["ba"].version, 1)
        self.assertEqual(updated.version, original_version)

    def test_skipping_ui_unlocks_dev(self) -> None:
        self.pipeline.stages["ui"].status = "pending"
        updated = skip_stage(self.pipeline, "ui", "backend-only task")
        self.assertEqual(updated.stages["ui"].status, "skipped")
        self.assertEqual(updated.stages["dev"].status, "pending")
        self.assertGreaterEqual(updated.stages["ui"].version, 1)

    def test_cannot_approve_empty_output(self) -> None:
        with self.assertRaises(ValueError):
            approve_stage(self.pipeline, "ba")

    def test_cannot_rerun_approved_stage_without_regenerate(self) -> None:
        self.pipeline.stages["ba"].output = {"assistant": "ba"}
        approve_stage(self.pipeline, "ba")
        allowed, reason = can_run_stage(self.pipeline, "ba", regenerate=False)
        self.assertFalse(allowed)
        self.assertIn("already approved", reason)

    def test_blocking_findings_prevent_approval(self) -> None:
        self.pipeline.stages["ba"].output = {"assistant": "ba"}
        self.pipeline.stages["ba"].unresolved_findings = [
            {"id": "finding_1", "severity": "blocking", "status": "open", "message": "Need acceptance criteria."}
        ]
        with self.assertRaises(ValueError):
            approve_stage(self.pipeline, "ba")

    def test_warnings_allow_approval(self) -> None:
        self.pipeline.stages["ba"].output = {"assistant": "ba"}
        self.pipeline.stages["ba"].unresolved_findings = [
            {"id": "finding_1", "severity": "warning", "status": "open", "message": "Review wording."}
        ]
        updated = approve_stage(self.pipeline, "ba")
        self.assertTrue(updated.stages["ba"].approved)
        self.assertEqual(updated.stages["ba"].unresolved_findings, [])
        self.assertEqual(updated.stages["ba"].resolved_findings[0]["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
