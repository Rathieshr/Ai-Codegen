from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.engineering_estimation import (
    EngineeringEstimationEngine,
    EngineeringEstimationRepository,
    build_engineering_estimation_router,
)
from backend.platform.shared import JsonMapStore


class PlanningEstimateSprint18Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.hierarchy = {
            "root": {
                "id": "epic-1", "type": "Epic", "title": "Modernize Device Health", "projectId": "project-1",
                "description": "Provide reliable device health operations.", "details": {
                    "repositoryContext": {"mode": "CodeIndexed", "existingComponents": ["DeviceService"], "snapshotId": "snapshot-1"},
                },
            },
            "nodes": [
                {"id": "epic-1", "type": "Epic", "title": "Modernize Device Health", "projectId": "project-1", "details": {}},
                {"id": "feature-1", "type": "Feature", "title": "Device Health Overview", "parentId": "epic-1", "details": {"dependencies": ["Telemetry API"]}},
                {"id": "story-1", "type": "Story", "title": "View Device Health", "parentId": "feature-1", "details": {"acceptanceCriteria": ["Operator can view current health.", "Unauthorized users are denied."], "risks": ["Permission regression"]}},
                {"id": "task-1", "type": "Task", "title": "Add Device Health API", "parentId": "story-1", "details": {"acceptanceCriteria": ["API returns current health."]}},
                {"id": "task-2", "type": "Task", "title": "Add permission tests", "parentId": "story-1", "details": {}},
            ],
        }
        self.provider_calls = []

        def planning_provider(planning_id, project_id):
            self.provider_calls.append((planning_id, project_id))
            if planning_id != "epic-1":
                raise LookupError(f"Planning Pack {planning_id} was not found.")
            return self.hierarchy

        self.engine = EngineeringEstimationEngine(
            EngineeringEstimationRepository(
                JsonMapStore(root / "estimates.json"),
                JsonMapStore(root / "outcomes.json"),
            ),
            planning_provider=planning_provider,
        )
        app = FastAPI()
        app.include_router(build_engineering_estimation_router(self.engine))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def test_get_estimates_the_complete_planning_pack(self):
        response = self.client.get("/planning/epic-1/estimate?projectId=project-1")
        self.assertEqual(200, response.status_code)
        result = response.json()
        self.assertEqual("hei-planning-pack-estimate-v1", result["schemaVersion"])
        self.assertEqual("epic-1", result["planningId"])
        self.assertEqual(2, result["effectiveEstimate"]["taskCount"])
        self.assertGreater(result["effectiveEstimate"]["engineeringDays"], 0)
        self.assertGreater(result["effectiveEstimate"]["engineeringHours"], 0)
        self.assertGreater(result["effectiveEstimate"]["storyPoints"], 0)
        self.assertGreaterEqual(result["effectiveEstimate"]["estimatedSprintCount"], 1)
        self.assertGreaterEqual(result["effectiveEstimate"]["developersNeeded"], 1)
        self.assertEqual(result["effectiveEstimate"]["suggestedTeamSize"], result["effectiveEstimate"]["developersNeeded"])
        self.assertIn(result["effectiveEstimate"]["risk"], {"Low", "Medium", "High", "Critical"})
        self.assertIn(result["effectiveEstimate"]["complexity"], {"Very Low", "Low", "Medium", "High", "Very High"})
        self.assertEqual([("epic-1", "project-1")], self.provider_calls)

    def test_put_preserves_ai_estimate_and_tracks_complete_user_override(self):
        generated = self.client.get("/planning/epic-1/estimate").json()
        original_hours = generated["aiEstimate"]["engineeringHours"]
        response = self.client.put("/planning/epic-1/estimate", json={
            "engineeringDays": 15,
            "engineeringHours": 120,
            "storyPoints": 34,
            "estimatedSprintCount": 2,
            "developersNeeded": 3,
            "confidence": 88,
            "risk": "High",
            "complexity": "Very High",
            "overrideReason": "Architecture review identified a new integration boundary.",
            "actor": "Tech Lead",
            "expectedEstimateId": generated["estimateId"],
            "expectedOverrideRevision": 0,
        })
        self.assertEqual(200, response.status_code)
        result = response.json()
        self.assertEqual(original_hours, result["aiEstimate"]["engineeringHours"])
        self.assertEqual(120, result["userEstimate"]["engineeringHours"])
        self.assertEqual(15, result["effectiveEstimate"]["engineeringDays"])
        self.assertEqual(34, result["effectiveEstimate"]["storyPoints"])
        self.assertEqual(3, result["effectiveEstimate"]["developersNeeded"])
        self.assertEqual("High", result["effectiveEstimate"]["risk"])
        self.assertEqual("Very High", result["effectiveEstimate"]["complexity"])
        self.assertEqual("Architecture review identified a new integration boundary.", result["override"]["reason"])
        self.assertEqual(1, result["override"]["revision"])
        self.assertEqual("Tech Lead", result["override"]["history"][0]["actor"])

    def test_override_can_derive_hours_from_days(self):
        result = self.client.put("/planning/epic-1/estimate", json={
            "engineeringDays": 8, "overrideReason": "Delivery planning adjustment.",
        }).json()
        self.assertEqual(64, result["effectiveEstimate"]["engineeringHours"])
        self.assertEqual(8, result["effectiveEstimate"]["engineeringDays"])

    def test_inconsistent_effort_and_stale_override_are_rejected(self):
        generated = self.client.get("/planning/epic-1/estimate").json()
        inconsistent = self.client.put("/planning/epic-1/estimate", json={
            "engineeringDays": 5, "engineeringHours": 80, "overrideReason": "Invalid mismatch.",
        })
        self.assertEqual(400, inconsistent.status_code)
        first = self.client.put("/planning/epic-1/estimate", json={
            "storyPoints": 21, "overrideReason": "Reviewed decomposition.", "expectedOverrideRevision": 0,
        })
        self.assertEqual(200, first.status_code)
        stale = self.client.put("/planning/epic-1/estimate", json={
            "storyPoints": 34, "overrideReason": "Stale browser.",
            "expectedEstimateId": generated["estimateId"], "expectedOverrideRevision": 0,
        })
        self.assertEqual(400, stale.status_code)
        self.assertIn("Reload", stale.json()["error"]["message"])

    def test_missing_pack_returns_not_found(self):
        response = self.client.get("/planning/missing/estimate")
        self.assertEqual(404, response.status_code)

    def test_workspace_shows_transparent_pack_estimate_and_exact_routes(self):
        source = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningCenter.tsx").read_text()
        for label in ("Engineering Days", "Story Points", "Hours", "Sprint Count", "Developers Needed", "Confidence", "Risk", "Complexity"):
            self.assertIn(label, source)
        self.assertIn("AI Estimate", source)
        self.assertIn("User Estimate", source)
        self.assertIn("Override Reason", source)
        self.assertIn("/planning/${encodeURIComponent(planningId)}/estimate", source)
        self.assertIn("method: 'PUT'", source)


if __name__ == "__main__":
    unittest.main()
