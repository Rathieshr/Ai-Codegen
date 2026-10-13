from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.platform.shared import JsonMapStore
from backend.repository_intelligence.api import build_repository_router
from backend.repository_intelligence.application import RepositoryDetectionService
from backend.repository_intelligence.domain import Repository, RepositorySnapshot
from backend.repository_intelligence.infrastructure import FileBackedRepositoryService, FileBackedSnapshotService
from backend.requirement_analysis import RequirementAnalysisService
from backend.requirement_intake import RequirementIngestionService


class EmptyMemory:
    def find_relevant_memory(self, _query):
        return {"results": [], "count": 0}


class RepositoryDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.repositories = FileBackedRepositoryService(root / "repositories.json")
        self.snapshots = FileBackedSnapshotService(root / "snapshots.json")
        self.ingestion = RequirementIngestionService(JsonMapStore(root / "requirements.json"))
        self.detector = RepositoryDetectionService(
            repository_service=self.repositories,
            snapshot_service=self.snapshots,
            memory_engine=EmptyMemory(),
            suggestion_store=JsonMapStore(root / "suggestions.json"),
            override_store=JsonMapStore(root / "overrides.json"),
            requirement_ingestion=self.ingestion,
        )
        self.repositories.create_repository(Repository(
            repository_id="device-repo", name="Device Operations", project_id="gridhub",
            url="https://dev.azure.com/hei/gridhub/_git/device-operations",
            metadata={"domain": "device health telemetry operations"},
        ))
        self.snapshots.save_snapshot(RepositorySnapshot(
            snapshot_id="device-v2", repository_id="device-repo", version=2,
            modules=["Device Health", "Telemetry", "Device Search"],
            languages={"TypeScript": 30, "C#": 18}, total_files=48,
        ))
        self.repositories.create_repository(Repository(
            repository_id="billing-repo", name="Billing Platform", project_id="finance",
            url="https://github.com/hei/billing", metadata={"domain": "invoice payment billing"},
        ))
        self.snapshots.save_snapshot(RepositorySnapshot(
            snapshot_id="billing-v1", repository_id="billing-repo",
            modules=["Invoices", "Payments"], languages={"Java": 40}, total_files=40,
        ))

    def tearDown(self):
        self.temp.cleanup()

    def request(self, requirement_id="requirement-device"):
        return {
            "requirementId": requirement_id,
            "projectId": "gridhub",
            "title": "Modernize Device Health Dashboard",
            "content": "Operations users filter unhealthy and offline devices using fresh telemetry.",
            "technologies": ["TypeScript"],
            "modules": ["Device Health"],
        }

    def test_detects_repository_from_project_modules_technology_and_keywords(self):
        result = self.detector.detect(self.request())
        selected = result["suggestedRepository"]
        self.assertEqual("device-repo", selected["repositoryId"])
        self.assertGreaterEqual(result["confidence"], 0.8)
        self.assertIn("Device Health", selected["matchedModules"])
        self.assertIn("TypeScript", selected["matchedTechnologies"])
        self.assertTrue(any("Azure DevOps project" in item for item in selected["evidence"]))

    def test_returns_ranked_alternatives_without_inventing_evidence(self):
        result = self.detector.detect(self.request())
        self.assertEqual("billing-repo", result["alternativeRepositories"][0]["repositoryId"])
        self.assertEqual("v1", result["alternativeRepositories"][0]["snapshotVersion"])
        self.assertNotIn("files", result["suggestedRepository"])

    def test_manual_override_is_persisted_and_updates_requirement_context(self):
        requirement = self.ingestion.ingest({
            "requirementId": "requirement-device", "sourceType": "PasteRequirement", "projectId": "gridhub",
            "title": "Device health", "content": "Show device health. Acceptance Criteria: Health status is visible.",
        })
        self.detector.detect(self.request(requirement["requirementId"]))
        result = self.detector.override(requirement["requirementId"], {
            "repositoryId": "billing-repo", "actor": "Reviewer", "reason": "Owned by billing team",
        })
        self.assertEqual("ManualOverride", result["suggestion"]["source"])
        self.assertEqual("billing-repo", result["suggestion"]["suggestedRepository"]["repositoryId"])
        updated = self.ingestion.get(requirement["requirementId"])
        self.assertEqual("billing-repo", updated["metadata"]["repositoryId"])
        self.assertNotEqual(requirement["contextVersion"], updated["contextVersion"])

    def test_requirement_analysis_approval_commits_suggested_repository(self):
        requirement = self.ingestion.ingest({
            "sourceType": "PasteRequirement", "projectId": "gridhub", "title": "Device health",
            "content": "Business Goal: Reduce device outages.\nFunctional Requirements: Operations users must filter device health.\nAcceptance Criteria: Filtering by Offline returns only offline devices.",
        })
        service = RequirementAnalysisService(
            JsonMapStore(Path(self.temp.name) / "analyses.json"),
            requirement_ingestion=self.ingestion,
            repository_detector=self.detector,
        )
        analyzed = service.analyze(requirement["requirementId"])
        self.assertEqual("device-repo", analyzed["repositorySuggestion"]["suggestedRepository"]["repositoryId"])
        approved = service.approve(requirement["requirementId"], "Product Owner")
        selected_context = self.ingestion.get(requirement["requirementId"])
        self.assertEqual("device-repo", selected_context["metadata"]["repositoryId"])
        self.assertEqual("Approved", approved["reviewStatus"])
        self.assertEqual(selected_context["contextVersion"], approved["approvedContextVersion"])

    def test_detection_and_suggestion_apis(self):
        module = SimpleNamespace(detection_service=self.detector, application=SimpleNamespace())
        app = FastAPI()
        app.include_router(build_repository_router(module))
        client = TestClient(app)
        detected = client.post("/repositories/detect", json=self.request())
        self.assertEqual(200, detected.status_code)
        suggestions = client.get("/repositories/suggestions", params={"requirementId": "requirement-device"})
        self.assertEqual(200, suggestions.status_code)
        self.assertEqual(1, suggestions.json()["count"])

    def test_no_registered_repositories_returns_honest_empty_result(self):
        empty = RepositoryDetectionService(
            repository_service=FileBackedRepositoryService(Path(self.temp.name) / "empty-repositories.json"),
            snapshot_service=FileBackedSnapshotService(Path(self.temp.name) / "empty-snapshots.json"),
            memory_engine=EmptyMemory(),
            suggestion_store=JsonMapStore(Path(self.temp.name) / "empty-suggestions.json"),
            override_store=JsonMapStore(Path(self.temp.name) / "empty-overrides.json"),
        )
        result = empty.detect(self.request("empty"))
        self.assertIsNone(result["suggestedRepository"])
        self.assertEqual(0.0, result["confidence"])
        self.assertEqual([], result["alternativeRepositories"])


if __name__ == "__main__":
    unittest.main()
