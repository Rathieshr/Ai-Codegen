from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.planning_center import PlanningCenterService, build_planning_center_router
from backend.project_intelligence import ProjectIntelligenceService


class PlanningApprovalSprint110Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"AI_GEN_DATA_DIR": self.temp.name}, clear=False)
        self.environment.start()
        self.intelligence = ProjectIntelligenceService()
        self.service = PlanningCenterService(
            artifact_provider=self.intelligence.list_artifacts,
            artifact_approver=self.intelligence.approve_artifact,
            artifact_rejecter=self.intelligence.archive_artifact,
            artifact_updater=self.intelligence.update_artifact_draft,
            artifact_creator=self.intelligence.save_artifact,
            artifact_transitioner=self.intelligence.transition_artifact,
        )
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        self.client = TestClient(app)
        self.artifact = self.intelligence.save_artifact({
            "artifact_type": "Planning Pack",
            "title": "Device Health Planning",
            "payload": {"description": "Initial planning scope", "dependencies": ["Telemetry"]},
            "source_item": {"id": "requirement-1", "type": "Requirement", "title": "Device Health"},
            "created_by": "Product Manager",
        })

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_review_approve_publish_and_history_are_versioned(self):
        reviewed = self.client.put(
            f"/planning/{self.artifact['artifact_id']}?actor=Product%20Manager",
            json={"status": "Review", "expectedVersion": 1},
        )
        self.assertEqual(200, reviewed.status_code)
        approved = self.client.post(f"/planning/{self.artifact['artifact_id']}/approve", json={
            "actor": "Engineering Director", "comments": "Scope and estimate approved.", "expectedVersion": 2,
        })
        self.assertEqual(200, approved.status_code)
        self.assertEqual("approved", approved.json()["state"])
        self.assertEqual(3, approved.json()["version"])
        self.assertEqual("Engineering Director", approved.json()["approved_by"])

        published = self.client.post(f"/planning/{self.artifact['artifact_id']}/publish", json={
            "actor": "Release Manager", "comments": "Ready for Azure DevOps synchronization.", "expectedVersion": 3,
        })
        self.assertEqual(200, published.status_code)
        self.assertEqual("published", published.json()["state"])
        self.assertEqual(4, published.json()["version"])
        projection = self.service.get(self.artifact["artifact_id"])
        self.assertEqual("Published", projection["status"])
        self.assertTrue(projection["azureDevOpsSyncReady"])

        history = self.client.get(f"/planning/{self.artifact['artifact_id']}/history")
        self.assertEqual(200, history.status_code)
        result = history.json()
        self.assertEqual("Published", result["currentState"])
        self.assertEqual(4, result["currentVersion"])
        self.assertEqual([1, 2, 3, 4], [item["version"] for item in result["history"]])
        self.assertEqual("Scope and estimate approved.", result["history"][1]["comments"])
        self.assertEqual("Release Manager", result["history"][-1]["actor"])

    def test_rejection_requires_comments_and_request_changes_restores_draft(self):
        missing = self.client.post(f"/planning/{self.artifact['artifact_id']}/reject", json={
            "actor": "Approver", "expectedVersion": 1,
        })
        self.assertEqual(409, missing.status_code)
        self.assertIn("Comments are required", missing.json()["error"]["message"])

        rejected = self.client.post(f"/planning/{self.artifact['artifact_id']}/reject", json={
            "actor": "Approver", "comments": "Acceptance scope is incomplete.", "expectedVersion": 1,
        })
        self.assertEqual("rejected", rejected.json()["state"])
        changes = self.client.post(f"/planning/{self.artifact['artifact_id']}/request-changes", json={
            "actor": "Approver", "comments": "Add measurable acceptance criteria.", "expectedVersion": 2,
        })
        self.assertEqual(200, changes.status_code)
        self.assertEqual("draft", changes.json()["state"])
        self.assertEqual(3, changes.json()["version"])

    def test_rollback_creates_a_new_draft_from_prior_snapshot(self):
        updated = self.client.put(f"/planning/{self.artifact['artifact_id']}?actor=Editor", json={
            "title": "Revised Device Health Planning", "status": "Review", "expectedVersion": 1,
        })
        self.assertEqual(2, updated.json()["version"])
        approved = self.client.post(f"/planning/{self.artifact['artifact_id']}/approve", json={
            "actor": "Approver", "expectedVersion": 2,
        })
        self.assertEqual(3, approved.json()["version"])
        rolled_back = self.client.post(f"/planning/{self.artifact['artifact_id']}/rollback", json={
            "targetVersion": 1, "actor": "Approver", "comments": "Restore the original scope.", "expectedVersion": 3,
        })
        self.assertEqual(200, rolled_back.status_code)
        self.assertEqual("draft", rolled_back.json()["state"])
        self.assertEqual(4, rolled_back.json()["version"])
        self.assertEqual("Device Health Planning", rolled_back.json()["title"])
        self.assertEqual(1, rolled_back.json()["rollback_to_version"])

    def test_invalid_and_stale_transitions_are_blocked(self):
        invalid = self.client.post(f"/planning/{self.artifact['artifact_id']}/publish", json={
            "actor": "Publisher", "expectedVersion": 1,
        })
        self.assertEqual(409, invalid.status_code)
        self.assertIn("Draft state", invalid.json()["error"]["message"])
        stale = self.client.post(f"/planning/{self.artifact['artifact_id']}/approve", json={
            "actor": "Approver", "expectedVersion": 99,
        })
        self.assertEqual(409, stale.status_code)
        self.assertIn("Reload", stale.json()["error"]["message"])

    def test_ui_exposes_enterprise_approval_actions_and_history(self):
        source = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningCenter.tsx").read_text()
        for label in ("Approve", "Reject", "Request Changes", "Publish", "Rollback", "Approval History"):
            self.assertIn(label, source)
        self.assertIn("'request-changes' | 'publish' | 'rollback'", source)
        self.assertIn("/history", source)


if __name__ == "__main__":
    unittest.main()
