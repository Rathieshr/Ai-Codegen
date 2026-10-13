from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_intelligence import build_ado_intelligence_router
from backend.ado_intelligence.repository import WorkItemRecommendationRepository
from backend.ado_intelligence.service import AdoWorkItemIntelligenceService, StaleRecommendationError
from backend.context_orchestration import ContextOrchestrator, PlanningContextSource, RequestKnowledgeContextSource
from backend.context_orchestration.models import ContextSourceResult, ContextSourceType
from backend.integrations.azure_devops.infrastructure import AzureDevOpsCacheStore
from backend.platform.shared import JsonMapStore


class RepositorySource:
    source_type = ContextSourceType.REPOSITORY

    def __init__(self, mode: str = "CodeIndexed") -> None:
        self.mode = mode

    def retrieve(self, request):
        if self.mode == "Unavailable":
            return ContextSourceResult(self.source_type, False, "Unavailable", warnings=["Repository unavailable."], diagnostics={"repositoryMode": "Unavailable"})
        if self.mode == "KnowledgeSnapshot":
            return ContextSourceResult(self.source_type, True, "Fresh", version="snapshot-1", items=[{"name": "Device Health", "content": "Device Health", "category": "Module", "broadContext": True}], diagnostics={"repositoryMode": "KnowledgeSnapshot"})
        return ContextSourceResult(self.source_type, True, "Fresh", version="snapshot-2", items=[{"path": "src/device-health.ts", "content": "src/device-health.ts", "category": "File", "directEvidence": True}], diagnostics={"repositoryMode": "CodeIndexed"})


class SpyOrchestrator:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.requests = []

    def orchestrate(self, request):
        self.requests.append(request)
        return self.inner.orchestrate(request)


class WriteForbidden:
    def __getattr__(self, name):
        raise AssertionError(f"ADO write/read-through service must not be called: {name}")


class WorkItemIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.cache = AzureDevOpsCacheStore(JsonMapStore(root / "ado-cache.json"))
        self.integration = SimpleNamespace(sync=SimpleNamespace(cache=self.cache), work_items=WriteForbidden())
        self.recommendations = WorkItemRecommendationRepository(JsonMapStore(root / "recommendations.json"), JsonMapStore(root / "analyses.json"))
        self.profile = {
            "knowledge_version": "kv-7",
            "knowledge_registry": {
                "modules": ["Device Health", "Telemetry", "Firmware Update"],
                "flows": ["Device Health Review Flow", "Firmware Rollout"],
                "standards": ["Role-based access", "Audit logging"],
            },
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def service(self, mode: str = "CodeIndexed") -> AdoWorkItemIntelligenceService:
        root = Path(self.temp.name)
        inner = ContextOrchestrator(
            sources=[PlanningContextSource(), RepositorySource(mode), RequestKnowledgeContextSource()],
            store=JsonMapStore(root / f"context-{mode}.json"),
        )
        self.spy = SpyOrchestrator(inner)
        return AdoWorkItemIntelligenceService(
            azure_devops=self.integration, context_orchestrator=self.spy,
            repository=self.recommendations, profile_provider=lambda: self.profile,
        )

    def cache_item(self, item_id: int, *, revision: int = 1, title: str = "Review Device Health Status", description: str | None = None, acceptance=None, item_type: str = "User Story") -> None:
        description = description or "Operations users lack current device health during investigations. The goal is to reduce outage investigation time and improve response decisions with current status."
        acceptance = acceptance if acceptance is not None else ["The dashboard must display device status within 2 seconds.", "Unauthorized users are denied access and the action is audited."]
        self.cache.upsert("project-1", "workItems", str(item_id), {"workItemId": item_id, "workItemType": item_type, "title": title, "description": description, "acceptanceCriteria": acceptance, "revision": revision}, revision_field="revision")

    def test_strong_requirement_uses_context_pipeline_and_returns_evidence(self):
        self.cache_item(101)
        result = self.service().analyze("101", {"projectId": "project-1"}, correlation_id="corr-strong")
        self.assertGreaterEqual(result["qualityScore"], 75)
        self.assertTrue(result["evidence"])
        self.assertEqual("corr-strong", result["correlationId"])
        self.assertEqual(1, len(self.spy.requests))
        self.assertEqual("Planning", self.spy.requests[0].purpose)

    def test_ambiguous_requirement_reports_missing_information(self):
        self.cache_item(102, title="Improve thing", description="Make it fast and user-friendly as needed.", acceptance=[])
        result = self.service("Unavailable").analyze("102", {"projectId": "project-1"})
        self.assertEqual("NeedsReview", result["status"])
        self.assertTrue(result["ambiguityFindings"])
        self.assertIn("Acceptance criteria", result["missingInformation"])

    def test_fragmented_acceptance_criteria_are_identified(self):
        self.cache_item(103, acceptance=["Device ID", "Severity", "Timestamp"])
        result = self.service().analyze("103", {"projectId": "project-1"})
        self.assertEqual("NeedsReview", result["acceptanceCriteriaQuality"]["status"])
        self.assertEqual(3, len(result["acceptanceCriteriaQuality"]["fragmentedCriteria"]))

    def test_unrelated_firmware_context_is_rejected(self):
        self.cache_item(104, title="Investigate Device Health Outage")
        result = self.service().analyze("104", {"projectId": "project-1"})
        self.assertNotIn("Firmware", " ".join(result["capabilityRecommendations"]))
        rejected = str(result["context"]["rejectedContext"])
        self.assertIn("Firmware", rejected)

    def test_duplicate_work_is_detected_from_synchronized_cache(self):
        self.cache_item(105, title="Review Device Health Status")
        self.cache_item(106, title="Review Device Health Status Dashboard")
        result = self.service().analyze("105", {"projectId": "project-1"})
        self.assertEqual("106", str(result["duplicateOrSimilarWork"][0]["workItemId"]))

    def test_repository_unavailable_reduces_confidence(self):
        self.cache_item(107)
        available = self.service("CodeIndexed").analyze("107", {"projectId": "project-1"})
        unavailable = self.service("Unavailable").analyze("107", {"projectId": "project-1", "regenerate": True})
        self.assertEqual("Unavailable", unavailable["context"]["repositoryMode"])
        self.assertLess(unavailable["confidence"], available["confidence"])

    def test_knowledge_snapshot_mode_is_explicit_and_has_no_fake_files(self):
        self.cache_item(108)
        result = self.service("KnowledgeSnapshot").analyze("108", {"projectId": "project-1"})
        self.assertEqual("KnowledgeSnapshot", result["context"]["repositoryMode"])
        repository_evidence = [item for item in result["evidence"] if item["source"] == "Repository"]
        self.assertFalse(any("/" in str(item["value"]) for item in repository_evidence))

    def test_revision_change_marks_recommendation_stale(self):
        self.cache_item(109, revision=3)
        service = self.service()
        result = service.analyze("109", {"projectId": "project-1"})
        recommendation_id = result["recommendations"][0]["recommendationId"]
        self.cache_item(109, revision=4)
        listed = service.list_recommendations("109", "project-1")
        self.assertEqual("Stale", next(item for item in listed["recommendations"] if item["recommendationId"] == recommendation_id)["status"])
        with self.assertRaises(StaleRecommendationError):
            service.approve(recommendation_id, "owner")

    def test_approval_is_local_and_never_writes_to_ado(self):
        self.cache_item(110)
        service = self.service()
        result = service.analyze("110", {"projectId": "project-1"})
        approved = service.approve(result["recommendations"][0]["recommendationId"], "product-owner")
        self.assertEqual("Approved", approved["status"])
        self.assertEqual("product-owner", approved["approvedBy"])

    def test_manual_requirement_and_api_lifecycle(self):
        service = self.service("Unavailable")
        app = FastAPI(); app.include_router(build_ado_intelligence_router(service)); client = TestClient(app)
        response = client.post("/ado-intelligence/work-items/manual-1/analyze", json={"projectId": "manual", "manualRequirement": {"title": "Add Device Search", "description": "Operations users need to find a device so that investigation time is reduced.", "acceptanceCriteria": ["Search results must return within 2 seconds."]}})
        self.assertEqual(200, response.status_code)
        recommendation_id = response.json()["recommendations"][0]["recommendationId"]
        self.assertEqual(200, client.post(f"/ado-intelligence/recommendations/{recommendation_id}/approve", json={"actor": "owner"}).status_code)
        listed = client.get("/ado-intelligence/work-items/manual-1/recommendations").json()
        self.assertGreater(listed["count"], 0)

    def test_synchronized_work_item_can_be_analyzed_without_request_body(self):
        self.cache_item(111)
        app = FastAPI(); app.include_router(build_ado_intelligence_router(self.service())); client = TestClient(app)
        response = client.post("/ado-intelligence/work-items/111/analyze")
        self.assertEqual(200, response.status_code)
        self.assertEqual("111", response.json()["workItemId"])


if __name__ == "__main__":
    unittest.main()
