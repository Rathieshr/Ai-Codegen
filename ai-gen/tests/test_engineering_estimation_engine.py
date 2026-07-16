import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.engineering_estimation import EngineeringEstimationEngine, EngineeringEstimationRepository, build_engineering_estimation_router
from backend.platform.shared import JsonMapStore


class Events:
    def __init__(self): self.items = []
    def publish(self, value): self.items.append(value); return value


class Platform:
    def __init__(self): self.events = Events()


class Memory:
    def find_relevant_memory(self, _query):
        return {"results": [{"id": "memory-1", "title": "Prior device health story", "approvalStatus": "Available"}, {"id": "rejected", "approvalStatus": "Rejected"}]}


class EngineeringEstimationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.platform = Platform()
        self.engine = EngineeringEstimationEngine(
            EngineeringEstimationRepository(JsonMapStore(root / "estimates.json"), JsonMapStore(root / "outcomes.json")),
            platform=self.platform, memory=Memory(),
        )

    def tearDown(self): self.temp.cleanup()

    def story(self, **changes):
        return {
            "artifact": {"id": "story-1", "type": "Story", "title": "View Device Health", "projectId": "project-1", "description": "Show device health on the operations dashboard."},
            "acceptanceCriteria": ["Operator can view current device status.", "Unauthorized users cannot view restricted devices."],
            **changes,
        }

    def test_small_story_is_decomposed_and_every_task_has_evidence(self):
        result = self.engine.estimate(self.story(repositoryContext={"mode": "CodeIndexed", "existingComponents": ["Dashboard"], "snapshotId": "snapshot-2"}))
        value = result["effectiveEstimate"]
        self.assertGreaterEqual(len(value["taskEstimates"]), 2)
        self.assertTrue(all(task["estimatedDurationHours"] > 0 and task["engineeringEvidence"] for task in value["taskEstimates"]))
        self.assertEqual("snapshot-2", value["repositorySnapshot"])
        self.assertEqual("EngineeringEstimateGenerated", self.platform.events.items[-1]["eventType"])

    def test_repository_reuse_increases_confidence_and_reduces_uncertainty(self):
        unavailable = self.engine.estimate(self.story(artifact={**self.story()["artifact"], "id": "story-none"}))
        reusable = self.engine.estimate(self.story(artifact={**self.story()["artifact"], "id": "story-reuse"}, repositoryContext={"existingComponents": ["Service", "Controller", "Tests"], "mode": "CodeIndexed"}))
        self.assertGreater(reusable["effectiveEstimate"]["confidence"], unavailable["effectiveEstimate"]["confidence"])
        self.assertGreater(reusable["effectiveEstimate"]["repositoryReuse"], unavailable["effectiveEstimate"]["repositoryReuse"])
        self.assertIn("no code evidence was invented", " ".join(unavailable["effectiveEstimate"]["warnings"]))

    def test_missing_acceptance_criteria_reduces_confidence(self):
        strong = self.engine.estimate(self.story(artifact={**self.story()["artifact"], "id": "strong"}))
        weak = self.engine.estimate(self.story(artifact={**self.story()["artifact"], "id": "weak"}, acceptanceCriteria=[]))
        self.assertLess(weak["effectiveEstimate"]["confidence"], strong["effectiveEstimate"]["confidence"])
        self.assertIn("Acceptance criteria are missing", " ".join(weak["effectiveEstimate"]["warnings"]))

    def test_high_complexity_security_and_database_work_adjusts_estimate(self):
        result = self.engine.estimate(self.story(
            artifact={"id": "story-secure", "type": "Story", "title": "Secure Device Data Migration", "description": "Add database migration, authorization, external API integration, telemetry, and performance validation."},
            dependencyAnalysis=["Identity provider", "External API"], riskAnalysis=["Security", "Migration", "Performance"],
        ))
        self.assertIn(result["effectiveEstimate"]["risk"], {"High", "Critical"})
        self.assertGreater(result["effectiveEstimate"]["engineeringHours"], 10)

    def test_epic_aggregates_features_stories_and_tasks(self):
        task = {"id": "task-1", "type": "Task", "title": "Add device API", "description": "Add controller and service."}
        story = {"id": "story-2", "type": "Story", "title": "Open device details", "acceptanceCriteria": ["Details load"], "tasks": [task]}
        feature = {"id": "feature-1", "type": "Feature", "title": "Device Details", "stories": [story]}
        result = self.engine.estimate({"artifact": {"id": "epic-1", "type": "Epic", "title": "Modernize Device Health", "features": [feature]}, "repositoryContext": {"existingComponents": ["DeviceService"]}})
        report = result["effectiveEstimate"]["report"]
        self.assertEqual(1, report["features"])
        self.assertGreaterEqual(report["stories"], 1)
        self.assertGreaterEqual(report["tasks"], 1)
        self.assertGreater(report["engineeringDays"], 0)

    def test_override_preserves_original_estimate_and_reason(self):
        generated = self.engine.estimate(self.story())
        original = generated["originalEstimate"]["engineeringHours"]
        overridden = self.engine.override(generated["estimateId"], {"engineeringHours": 18, "storyPoints": 8, "overrideReason": "Architecture review found an extra integration."}, actor="lead")
        self.assertEqual(original, overridden["originalEstimate"]["engineeringHours"])
        self.assertEqual(18, overridden["effectiveEstimate"]["engineeringHours"])
        self.assertEqual("lead", overridden["userEstimate"]["overriddenBy"])

    def test_recalculation_versions_estimates(self):
        generated = self.engine.estimate(self.story())
        reused = self.engine.estimate(self.story())
        self.assertEqual(generated["estimateId"], reused["estimateId"])
        recalculated = self.engine.recalculate({"estimateId": generated["estimateId"], **self.story(), "riskAnalysis": ["New integration"]})
        self.assertEqual(2, recalculated["version"])
        self.assertEqual(generated["estimateId"], recalculated["parentEstimateId"])

    def test_learning_record_preserves_actual_outcome(self):
        generated = self.engine.estimate(self.story())
        outcome = self.engine.learn(generated["estimateId"], {"actualDurationHours": 22, "actualStoryPoints": 5, "reviewCount": 2, "prIterations": 3, "reopenedWork": 1, "regressionIssues": 0})
        self.assertEqual(22, outcome["actualDurationHours"])
        self.assertEqual(3, outcome["prIterations"])
        self.assertEqual("EngineeringEstimateLearned", self.platform.events.items[-1]["eventType"])

    def test_estimation_report_and_api_contracts(self):
        app = FastAPI()
        app.include_router(build_engineering_estimation_router(self.engine))
        client = TestClient(app)
        generated = client.post("/planning/estimate", json=self.story())
        self.assertEqual(200, generated.status_code)
        estimate_id = generated.json()["estimateId"]
        summary = client.get(f"/planning/estimate-summary/{estimate_id}")
        self.assertEqual(200, summary.status_code)
        self.assertIn("topEstimationDrivers", summary.json())
        task = client.post("/planning/task-estimate", json={"artifact": {"id": "task-api", "title": "Add API"}})
        self.assertEqual("Task", task.json()["artifactType"])


if __name__ == "__main__":
    unittest.main()
