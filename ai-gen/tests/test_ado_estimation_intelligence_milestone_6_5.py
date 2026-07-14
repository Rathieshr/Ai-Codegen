from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_intelligence.api import build_ado_intelligence_router
from backend.ado_intelligence.estimation_repository import EstimationRepository
from backend.ado_intelligence.estimation_service import EstimationIntelligenceService
from backend.ado_intelligence.repository import WorkItemRecommendationRepository
from backend.integrations.azure_devops.infrastructure.sync_store import AzureDevOpsCacheStore
from backend.platform.shared import JsonMapStore


class FakeMemory:
    def find_relevant_memory(self, query):
        return {
            "results": [{
                "id": "memory-1", "projectId": "project-1", "title": "Device health implementation",
                "searchScore": 12, "matchReasons": ["module"], "approvalStatus": "Available",
            }],
            "count": 1,
        }


class EstimationIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.cache = AzureDevOpsCacheStore(JsonMapStore(root / "cache.json"))
        self.recommendations = WorkItemRecommendationRepository(
            JsonMapStore(root / "recommendations.json"), JsonMapStore(root / "analyses.json")
        )
        self.estimates = EstimationRepository(JsonMapStore(root / "estimates.json"), JsonMapStore(root / "outcomes.json"))
        azure = SimpleNamespace(sync=SimpleNamespace(cache=self.cache))
        self.service = EstimationIntelligenceService(
            azure_devops=azure, estimates=self.estimates, recommendations=self.recommendations,
            engineering_memory=FakeMemory(),
        )

    def tearDown(self):
        self.temp.cleanup()

    def put(self, work_item_id, **changes):
        value = {
            "workItemId": str(work_item_id), "workItemType": "User Story", "title": "View device health",
            "description": "Operations users review current device health.", "state": "New", "revision": 1,
            "acceptanceCriteria": ["Show current health status", "Restrict access by role"],
            "teamId": "team-a", "storyPoints": None,
        }
        value.update(changes)
        self.cache.upsert("project-1", "workItems", str(work_item_id), value)
        return value

    def generate(self, work_item_id="101", **request):
        return self.service.estimate(str(work_item_id), {"projectId": "project-1", **request})

    def test_new_project_without_history_is_explicitly_uncalibrated(self):
        self.put("101")
        result = self.generate(repositoryImpact={"mode": "KnowledgeSnapshot", "modules": ["Asset Health"]})
        self.assertEqual("Uncalibrated", result["calibration"]["calibrationScope"])
        self.assertIn(result["uncertainty"]["level"], {"Medium", "High"})
        self.assertNotIn("hours", str(result["effortRange"]).lower())
        self.assertGreaterEqual(len(result["suggestedTasks"]), 3)

    def test_project_history_calibrates_after_three_completed_outcomes(self):
        for index, days in enumerate((2.0, 3.0, 4.0), start=1):
            self.put(str(index), title=f"Completed health story {index}", state="Closed", storyPoints=5, actualCycleTimeDays=days)
        accuracy = self.service.accuracy("project-1", "team-a")
        self.assertEqual("Team", accuracy["calibrationScope"])
        self.assertEqual(3, accuracy["sampleCount"])
        self.assertIsInstance(accuracy["accuracy"], float)
        self.assertTrue(all(sample["source"] == "Synchronized Azure DevOps history" for sample in accuracy["samples"]))

    def test_large_cross_module_story_receives_large_relative_estimate(self):
        self.put("101", acceptanceCriteria=[f"Acceptance outcome {index}" for index in range(1, 7)])
        result = self.generate(repositoryImpact={
            "mode": "CodeIndexed", "modules": ["Asset Health", "Telemetry", "Authorization", "Dashboard"],
            "files": ["one.ts", "two.py", "three.cs", "four.test.ts"],
        }, dependencies=["Telemetry contract", "Role matrix"])
        self.assertGreaterEqual(result["storyPoints"], 8)
        self.assertTrue(result["repositoryImpact"]["crossModule"])

    def test_small_documentation_task_uses_small_range_and_documentation_tasks(self):
        self.put("102", workItemType="Task", title="Update README documentation", description="Correct setup instructions.", acceptanceCriteria=["README contains the current command"])
        result = self.generate("102", repositoryImpact={"mode": "CodeIndexed", "files": ["README.md"]})
        self.assertEqual(1, result["storyPoints"])
        self.assertEqual("0.5-1 day", result["effortRange"]["development"])
        self.assertEqual("Documentation", result["suggestedTasks"][0]["workArea"])

    def test_missing_acceptance_and_repository_context_report_high_uncertainty(self):
        self.put("103", acceptanceCriteria=[], description="Improve it.")
        result = self.generate("103")
        self.assertEqual("High", result["uncertainty"]["level"])
        self.assertTrue(any("Acceptance criteria" in value for value in result["blockers"]))
        self.assertLess(result["confidence"], .5)

    def test_similar_completed_work_is_returned_as_evidence(self):
        self.put("100", title="View device health status", state="Closed", storyPoints=5, actualCycleTimeDays=3)
        self.put("101", title="View device health details")
        result = self.generate(repositoryImpact={"mode": "CodeIndexed", "modules": ["Asset Health"]})
        self.assertEqual("100", result["similarHistoricalItems"][0]["workItemId"])
        self.assertTrue(any(item["type"] == "HistoricalWork" for item in result["evidence"]))
        self.assertEqual(1, result["memoryContext"]["count"])

    def test_human_edit_and_accept_create_approved_automation_recommendation(self):
        self.put("101")
        generated = self.generate(repositoryImpact={"mode": "CodeIndexed", "modules": ["Asset Health"]})
        edited = self.service.edit(generated["estimateId"], {"storyPoints": 8, "editReason": "Cross-team dependency"})
        self.assertEqual("Edited", edited["status"])
        self.assertEqual(generated["estimateId"], edited["parentEstimateId"])
        accepted = self.service.accept(edited["estimateId"], "product-owner")
        recommendation = self.recommendations.get(accepted["automationRecommendationId"])
        self.assertEqual("StoryPointRecommendation", recommendation.recommendation_type)
        self.assertEqual("Approved", recommendation.status.value)
        self.assertEqual(8, recommendation.proposed_value["points"])

    def test_actual_outcome_feedback_updates_calibration_and_quality_signals(self):
        estimate_ids = []
        for index in range(3):
            self.put(str(200 + index), title=f"Device health slice {index}")
            estimate = self.generate(str(200 + index), repositoryImpact={"mode": "CodeIndexed", "modules": ["Asset Health"]})
            estimate_ids.append(estimate["estimateId"])
        for index, estimate_id in enumerate(estimate_ids):
            result = self.service.record_outcome(estimate_id, {
                "actualCycleTimeDays": 5 + index, "reopenCount": 1, "prIterations": 2, "escapedDefects": index,
            })
        self.assertEqual("Team", result["calibration"]["calibrationScope"])
        self.assertEqual(3, result["calibration"]["qualitySignals"]["reopens"])
        self.assertEqual(6, result["calibration"]["qualitySignals"]["prIterations"])

    def test_estimation_routes_expose_generation_retrieval_and_accuracy(self):
        self.put("101")
        facade = SimpleNamespace(estimation=self.service)
        app = FastAPI()
        app.include_router(build_ado_intelligence_router(facade))
        client = TestClient(app)
        generated = client.post("/ado-intelligence/work-items/101/estimate", json={
            "projectId": "project-1", "repositoryImpact": {"mode": "CodeIndexed", "modules": ["Asset Health"]},
        })
        self.assertEqual(200, generated.status_code)
        loaded = client.get("/ado-intelligence/work-items/101/estimate?projectId=project-1")
        self.assertEqual(generated.json()["estimateId"], loaded.json()["estimateId"])
        accuracy = client.get("/ado-intelligence/projects/project-1/estimation-accuracy?teamId=team-a")
        self.assertEqual("Uncalibrated", accuracy.json()["calibrationScope"])


if __name__ == "__main__":
    unittest.main()
