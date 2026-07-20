from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.engineering_estimation import EngineeringEstimationEngine, EngineeringEstimationRepository
from backend.platform.shared import JsonMapStore
from backend.planning_integration import RequirementPlanningService, build_requirement_planning_router
from backend.repository_intelligence.application import RepositoryDetectionService
from backend.repository_intelligence.domain import Repository, RepositorySnapshot
from backend.repository_intelligence.infrastructure import FileBackedRepositoryService, FileBackedSnapshotService
from backend.requirement_analysis import RequirementAnalysisService
from backend.requirement_intake import RequirementIngestionService, RequirementIntakeService


CONTENT = """Business Goal:
Reduce the time required to identify unhealthy devices.
Functional Requirements:
- Operations users must filter devices by health status.
Non Functional Requirements:
- Results must load within 2 seconds.
Acceptance Criteria:
- Filtering by Offline returns only offline devices.
Dependencies:
- Requires the Device Health API service.
Risks:
- Stale telemetry may delay status changes.
"""


class ContextSpy:
    def __init__(self):
        self.requests = []

    def orchestrate(self, request):
        self.requests.append(request)
        return {
            "capsuleId": f"capsule-{len(self.requests)}", "status": "Ready", "confidence": 0.91,
            "freshnessStatus": "Fresh", "sourceSummary": [
                {"sourceType": "Repository", "available": True, "selectedCount": 1, "freshness": "Fresh", "version": "v3"},
                {"sourceType": "EngineeringMemory", "available": True, "selectedCount": 0, "freshness": "Fresh", "version": "1"},
            ], "warnings": [], "blockers": [],
        }


class EmptyMemory:
    def find_relevant_memory(self, _query):
        return {"results": [], "count": 0}


class RequirementPlanningIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.repositories = FileBackedRepositoryService(root / "repositories.json")
        self.snapshots = FileBackedSnapshotService(root / "snapshots.json")
        self.repositories.create_repository(Repository(
            repository_id="device-repository", name="Device Operations", project_id="gridhub",
            url="https://dev.azure.com/hei/gridhub/_git/device-operations",
            metadata={"domain": "device health telemetry operations"},
        ))
        self.snapshots.save_snapshot(RepositorySnapshot(
            snapshot_id="snapshot-device-v3", repository_id="device-repository", version=3,
            modules=["Device Health", "Telemetry"], languages={"TypeScript": 20, "C#": 12}, total_files=32,
        ))
        self.ingestion = RequirementIngestionService(
            JsonMapStore(root / "requirement-contexts.json"),
            work_item_provider=lambda _project, _item: {
                "title": "Device Health Work Item", "description": CONTENT,
                "acceptanceCriteria": ["Filtering by Offline returns only offline devices."], "revision": 7,
            },
        )
        detector = RepositoryDetectionService(
            repository_service=self.repositories, snapshot_service=self.snapshots, memory_engine=EmptyMemory(),
            suggestion_store=JsonMapStore(root / "repository-suggestions.json"),
            override_store=JsonMapStore(root / "repository-overrides.json"),
            requirement_ingestion=self.ingestion,
        )
        self.analysis = RequirementAnalysisService(
            JsonMapStore(root / "analyses.json"), requirement_ingestion=self.ingestion, repository_detector=detector,
        )
        self.context = ContextSpy()
        self.artifacts = []

        def write_artifact(item):
            record = {
                **item, "artifact_id": f"planning-pack-{len(self.artifacts) + 1}",
                "version": 1, "created_on": "2026-07-20T00:00:00Z",
            }
            self.artifacts.append(record)
            return record

        self.intake = RequirementIntakeService(
            JsonMapStore(root / "intake.json"), context_orchestrator=self.context,
            artifact_writer=write_artifact, ingestion_service=self.ingestion, analysis_service=self.analysis,
        )
        self.estimation = EngineeringEstimationEngine(EngineeringEstimationRepository(
            JsonMapStore(root / "estimates.json"), JsonMapStore(root / "outcomes.json"),
        ))
        repository_application = type("RepositoryApplication", (), {
            "get_current_snapshot": lambda _self, repository_id: self.snapshots.get_latest_snapshot(repository_id).to_dict(),
        })()
        self.service = RequirementPlanningService(
            JsonMapStore(root / "requirement-planning.json"),
            requirement_ingestion=self.ingestion, requirement_analysis=self.analysis,
            requirement_intake=self.intake, estimation_engine=self.estimation,
            artifact_provider=lambda: {"artifacts": self.artifacts, "count": len(self.artifacts)},
            repository_intelligence=repository_application,
        )

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, source_type: str, *, title: str = "Device Health", **extra):
        request = {"sourceType": source_type, "projectId": "gridhub", "title": title, **extra}
        if source_type == "PasteRequirement":
            request["content"] = CONTENT
        elif source_type == "UploadDocument":
            request["document"] = {"name": extra.get("fileName", "requirement.md"), "mediaType": "text/markdown", "content": CONTENT}
        elif source_type == "MeetingTranscript":
            request["transcript"] = CONTENT
        elif source_type == "AzureDevOpsWorkItem":
            request["workItemId"] = "245"
        context = self.ingestion.ingest(request)
        self.analysis.analyze(context["requirementId"])
        self.analysis.approve(context["requirementId"], "Product Owner")
        return self.ingestion.get(context["requirementId"])

    def test_all_supported_requirement_sources_generate_validated_planning_packs(self):
        sources = [
            ("PasteRequirement", "Manual Requirement", {}),
            ("UploadDocument", "Device Health PRD", {"fileName": "device-health-prd.md"}),
            ("UploadDocument", "Device Health BRD", {"fileName": "device-health-brd.md"}),
            ("MeetingTranscript", "Device Health Review", {}),
            ("AzureDevOpsWorkItem", "Ignored by synchronized work item", {}),
        ]
        for source, title, extra in sources:
            with self.subTest(source=source, title=title):
                requirement = self.prepare(source, title=title, **extra)
                result = self.service.from_requirement({"requirementId": requirement["requirementId"], "actor": "Planner"})
                self.assertEqual("RequirementIntelligence", result["entryPoint"])
                self.assertEqual("RequirementSummary", result["requirementSummary"]["summaryType"])
                self.assertEqual(source, result["requirementSummary"]["sourceType"])
                self.assertTrue(result["planningPackId"])
                self.assertTrue(result["estimateId"])
                self.assertIn(result["planningPreview"]["validation"]["status"], {"ReadyForApproval", "NeedsReview"})

    def test_planning_agent_context_consumes_summary_not_request_text(self):
        requirement = self.prepare("PasteRequirement")
        result = self.service.from_requirement({
            "requirementId": requirement["requirementId"],
            "title": "RAW TITLE MUST NOT WIN", "content": "RAW CONTENT MUST NOT REACH PLANNING",
        })
        artifact = self.context.requests[0].artifact
        self.assertEqual("RequirementSummary", artifact["planningSource"])
        self.assertEqual(result["requirementSummary"], artifact["requirementSummary"])
        self.assertNotIn("RAW CONTENT", artifact["description"])
        self.assertEqual("RequirementSummary", self.artifacts[0]["payload"]["planningSource"])

    def test_repository_detection_reaches_estimation_and_preview(self):
        requirement = self.prepare("PasteRequirement")
        result = self.service.generate({"requirementId": requirement["requirementId"]})
        summary = result["requirementSummary"]
        self.assertEqual("device-repository", summary["repository"]["repositoryId"])
        self.assertGreater(summary["repository"]["confidence"], 0)
        self.assertEqual("snapshot-device-v3", result["engineeringEstimation"]["repositorySnapshot"])
        self.assertEqual("CodeIndexed", result["planningPreview"]["validation"]["repositoryMode"])

    def test_generation_is_idempotent_for_same_approved_summary(self):
        requirement = self.prepare("PasteRequirement")
        first = self.service.generate({"requirementId": requirement["requirementId"]})
        second = self.service.generate({"requirementId": requirement["requirementId"]})
        self.assertEqual(first["planningPackId"], second["planningPackId"])
        self.assertEqual(first["estimateId"], second["estimateId"])
        self.assertEqual(1, len(self.artifacts))

    def test_raw_planning_input_and_unapproved_summary_are_blocked(self):
        with self.assertRaisesRegex(ValueError, "Raw planning input cannot bypass"):
            self.service.generate({"title": "Bypass", "content": "Do planning directly"})
        requirement = self.ingestion.ingest({
            "sourceType": "PasteRequirement", "projectId": "gridhub", "title": "Unreviewed", "content": CONTENT,
        })
        self.analysis.analyze(requirement["requirementId"])
        with self.assertRaisesRegex(ValueError, "approval is required"):
            self.service.generate({"requirementId": requirement["requirementId"]})

    def test_preview_detects_stale_requirement_summary(self):
        requirement = self.prepare("PasteRequirement")
        result = self.service.generate({"requirementId": requirement["requirementId"]})
        self.analysis.edit(requirement["requirementId"], {
            "title": "Updated Device Health", "content": CONTENT + "\nConstraints:\n- Only approved regions are included.",
        })
        with self.assertRaisesRegex(ValueError, "approval is required|stale"):
            self.service.preview({"planningPackId": result["planningPackId"]})

    def test_required_planning_apis_and_preview_contract(self):
        requirement = self.prepare("PasteRequirement")
        app = FastAPI()
        app.include_router(build_requirement_planning_router(self.service))
        client = TestClient(app)
        generated = client.post("/planning/from-requirement", json={"requirementId": requirement["requirementId"]})
        self.assertEqual(200, generated.status_code)
        preview = client.post("/planning/preview", json={"planningPackId": generated.json()["planningPackId"]})
        self.assertEqual(200, preview.status_code)
        self.assertEqual("RequirementSummary", preview.json()["planningPreview"]["source"])
        direct = client.post("/planning/generate", json={"title": "Bypass"})
        self.assertEqual(400, direct.status_code)
        self.assertEqual("invalid_requirement_planning", direct.json()["error"]["code"])


if __name__ == "__main__":
    unittest.main()
