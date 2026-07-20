from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.platform.shared import JsonMapStore
from backend.requirement_intake import (
    RequirementIngestionService,
    RequirementIntakeService,
    RequirementSourceType,
    build_requirement_intake_router,
)


ROOT = Path(__file__).resolve().parents[1]


class ContextOrchestratorSpy:
    def __init__(self) -> None:
        self.requests = []

    def orchestrate(self, request):
        self.requests.append(request)
        return {
            "capsuleId": "capsule-requirement-source",
            "status": "Ready",
            "confidence": 0.88,
            "freshnessStatus": "Fresh",
            "sourceSummary": [],
            "warnings": [],
            "blockers": [],
        }


class RequirementSourceFrameworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work_items = {
            "245": {
                "workItemId": "245",
                "workItemType": "User Story",
                "title": "Review offline devices",
                "description": "Operations users need to find devices that stopped reporting.",
                "acceptanceCriteria": ["Offline devices are visible", "Results can be filtered by feeder"],
                "revision": 7,
            }
        }
        self.ingestion = RequirementIngestionService(
            JsonMapStore(self.root / "contexts.json"),
            work_item_provider=lambda project_id, item_id: self.work_items.get(item_id) if project_id == "gridhub" else None,
        )
        self.context = ContextOrchestratorSpy()
        self.artifacts = []
        self.intake = RequirementIntakeService(
            JsonMapStore(self.root / "planning.json"),
            ingestion_service=self.ingestion,
            context_orchestrator=self.context,
            artifact_writer=self._write_artifact,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_artifact(self, value):
        artifact = {**value, "artifact_id": f"pack-{len(self.artifacts) + 1}"}
        self.artifacts.append(artifact)
        return artifact

    @staticmethod
    def _base(**values):
        return {
            "projectId": "gridhub",
            "projectName": "GridHub",
            "repositoryId": "repo-1",
            "branch": "main",
            "actor": "Product Owner",
            **values,
        }

    def test_paste_requirement_is_persisted_as_ready_context(self):
        result = self.ingestion.ingest(self._base(
            sourceType="PasteRequirement",
            title="Improve device health",
            content="  Operations users need offline device visibility.  ",
        ))
        self.assertEqual("Ready", result["status"])
        self.assertTrue(result["planningReady"])
        self.assertEqual("PasteRequirement", result["sourceType"])
        self.assertEqual("Operations users need offline device visibility.", result["normalizedRequirement"])
        self.assertEqual(result, self.ingestion.get(result["requirementId"]))
        self.assertEqual("Ready", self.ingestion.status(result["requirementId"])["status"])

    def test_uploaded_document_creates_document_evidence(self):
        result = self.ingestion.ingest(self._base(
            sourceType="UploadDocument",
            title="Alarm center PRD",
            document={"name": "alarm-center.md", "mediaType": "text/markdown", "content": "# Goal\n\nReview active alarms."},
        ))
        document = result["documents"][0]
        self.assertEqual("alarm-center.md", document["name"])
        self.assertEqual("text/markdown", document["mediaType"])
        self.assertGreater(document["sizeBytes"], 0)
        self.assertEqual(64, len(document["contentHash"]))

    def test_meeting_transcript_is_a_first_class_source(self):
        result = self.ingestion.ingest(self._base(
            sourceType="MeetingTranscript",
            title="Device health review",
            transcript="Owner: We need health filtering.\nEngineer: Include offline status.",
        ))
        self.assertEqual("MeetingTranscript", result["sourceType"])
        self.assertEqual("MeetingTranscript", result["documents"][0]["source"])
        self.assertIn("offline status", result["normalizedRequirement"])

    def test_azure_devops_source_uses_synchronized_work_item(self):
        result = self.ingestion.ingest(self._base(sourceType="AzureDevOpsWorkItem", workItemId="245"))
        self.assertEqual("Review offline devices", result["title"])
        self.assertEqual("245", result["metadata"]["sourceReference"])
        self.assertEqual("7", result["metadata"]["sourceRevision"])
        self.assertIn("Results can be filtered by feeder", result["normalizedRequirement"])

    def test_future_sources_are_explicit_placeholders(self):
        for source in ("Confluence", "SharePoint", "Notion", "Email", "RestApi"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "future connector"):
                self.ingestion.ingest(self._base(sourceType=source, title="Ignored", content="Ignored"))

    def test_planning_consumes_persisted_context_not_raw_input(self):
        ingested = self.ingestion.ingest(self._base(
            sourceType="PasteRequirement", title="Device visibility", content="Canonical normalized requirement.",
        ))
        result = self.intake.submit({
            "requirementContextId": ingested["requirementId"],
            "title": "RAW TITLE MUST NOT WIN",
            "content": "RAW CONTENT MUST NOT REACH PLANNING",
        })
        artifact = self.context.requests[0].artifact
        self.assertEqual("Device visibility", artifact["title"])
        self.assertEqual("Canonical normalized requirement.", artifact["description"])
        self.assertEqual(ingested["requirementId"], artifact["requirementContextId"])
        self.assertEqual("pack-1", result["planningPackId"])

    def test_legacy_intake_auto_ingests_before_planning(self):
        result = self.intake.submit(self._base(
            inputType="Business Requirement", title="Legacy caller", content="Still enters through ingestion.",
        ))
        stored = self.ingestion.get(result["requirementId"])
        self.assertIsNotNone(stored)
        self.assertEqual("PasteRequirement", stored["sourceType"])
        self.assertEqual(stored["contentHash"], self.context.requests[0].artifact["contentHash"])

    def test_ingestion_and_status_apis_are_exposed(self):
        app = FastAPI()
        app.include_router(build_requirement_intake_router(self.intake, self.ingestion))
        client = TestClient(app)
        response = client.post("/requirements/ingest", json=self._base(
            sourceType="PasteRequirement", title="API intake", content="Create one canonical context.",
        ))
        self.assertEqual(200, response.status_code)
        requirement_id = response.json()["requirementId"]
        self.assertEqual("Ready", client.get(f"/requirements/{requirement_id}/status").json()["status"])
        self.assertEqual("API intake", client.get(f"/requirements/{requirement_id}").json()["title"])
        future = client.post("/requirements/ingest", json=self._base(sourceType="Confluence"))
        self.assertEqual(400, future.status_code)
        self.assertEqual("invalid_requirement_source", future.json()["error"]["code"])

    def test_ui_exposes_source_workflows_and_two_stage_pipeline(self):
        source = (ROOT / "azure-devops-extension/src/newRequirementWorkspace.tsx").read_text()
        for label in ("Paste Requirement", "Upload Document", "Azure DevOps Work Item", "Meeting Transcript"):
            self.assertIn(label, source)
        for future in ("Confluence", "SharePoint", "Notion", "Email", "REST API"):
            self.assertIn(future, source)
        self.assertLess(source.index("/requirements/ingest"), source.index("/planning/from-requirement"))
        self.assertIn("requirementId: ingestion.requirementId", source)
        self.assertNotIn("/requirements/intake", source)

    def test_source_type_aliases_preserve_existing_callers(self):
        self.assertEqual(RequirementSourceType.PASTE_REQUIREMENT, RequirementSourceType.parse("Business Requirement"))
        self.assertEqual(RequirementSourceType.UPLOAD_DOCUMENT, RequirementSourceType.parse("PRD"))
        self.assertEqual(RequirementSourceType.MEETING_TRANSCRIPT, RequirementSourceType.parse("Meeting Notes"))


if __name__ == "__main__":
    unittest.main()
