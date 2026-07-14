from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.platform.shared import JsonMapStore
from backend.requirement_intake import RequirementIntakeService, build_requirement_intake_router


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "azure-devops-extension"


class FakeContextOrchestrator:
    def __init__(self) -> None:
        self.requests = []

    def orchestrate(self, request):
        self.requests.append(request)
        return {
            "capsuleId": "capsule-intake-1",
            "status": "Ready",
            "confidence": 0.91,
            "freshnessStatus": "Fresh",
            "sourceSummary": [
                {"sourceType": "Planning", "available": True, "selectedCount": 1, "freshness": "Fresh", "version": "1"},
                {"sourceType": "Repository", "available": True, "selectedCount": 2, "freshness": "Fresh", "version": "snapshot-4"},
                {"sourceType": "KnowledgeRegistry", "available": True, "selectedCount": 2, "freshness": "Fresh", "version": "knowledge-3"},
                {"sourceType": "EngineeringMemory", "available": True, "selectedCount": 1, "freshness": "Fresh", "version": "memory-2"},
            ],
            "warnings": [],
            "blockers": [],
        }


class AzureDevOpsSingleHubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.context = FakeContextOrchestrator()
        self.artifacts = []
        self.service = RequirementIntakeService(
            JsonMapStore(Path(self.temp.name) / "requirements.json"),
            context_orchestrator=self.context,
            artifact_writer=self.write_artifact,
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_artifact(self, value):
        record = {**value, "artifact_id": f"pack-{len(self.artifacts) + 1}", "version": 1}
        self.artifacts.append(record)
        return record

    def request(self):
        return {
            "inputType": "Business Requirement",
            "title": "Improve device health operations",
            "content": "Operations users need a reliable view of unhealthy and offline devices.",
            "organization": "Hubbell",
            "projectId": "project-1",
            "projectName": "GridHub",
            "teamId": "team-1",
            "repositoryId": "repo-1",
            "branch": "main",
            "actor": "Product Owner",
            "correlationId": "corr-single-hub",
        }

    def test_manifest_contributes_exactly_one_project_hub(self):
        manifest = json.loads((EXTENSION / "azure-devops-extension.hei.json").read_text())
        hubs = [item for item in manifest["contributions"] if item["type"] == "ms.vss-web.hub"]
        groups = [item for item in manifest["contributions"] if item["type"] == "ms.vss-web.hub-group"]
        self.assertEqual(1, len(hubs))
        self.assertEqual(1, len(groups))
        self.assertEqual("HEI", groups[0]["properties"]["name"])
        self.assertEqual("dist/hei/index.html", hubs[0]["properties"]["uri"])
        self.assertEqual(["ms.vss-web.project-hub-groups-collection"], groups[0]["targets"])

    def test_existing_work_item_page_and_open_action_are_preserved(self):
        manifest = json.loads((EXTENSION / "azure-devops-extension.hei.json").read_text())
        types = {item["type"]: item for item in manifest["contributions"] if item["type"] in {"ms.vss-work-web.work-item-form-page", "ms.vss-web.action"}}
        self.assertEqual("projectIntelligenceTab.html", types["ms.vss-work-web.work-item-form-page"]["properties"]["uri"])
        self.assertEqual("Open in HEI", types["ms.vss-web.action"]["properties"]["text"])

    def test_hub_uses_internal_routing_and_lazy_pages(self):
        source = (EXTENSION / "src/heiApp.tsx").read_text()
        adapter = (EXTENSION / "src/host/AzureDevOpsHostAdapter.ts").read_text()
        for route in ("overview", "new-requirement", "planning", "repository", "execution", "approvals", "azure-devops", "agents", "activity", "settings"):
            self.assertIn(f"'{route}'", source)
        self.assertIn("window.history.pushState", adapter)
        self.assertIn("lazy(() => import", source)
        self.assertIn('logoSrc="../../static/hei-logo.png"', source)
        self.assertNotIn("window.location.reload", source)

    def test_azure_devops_sdk_is_isolated_to_host_adapter(self):
        app_source = (EXTENSION / "src/heiApp.tsx").read_text()
        host_source = (EXTENSION / "src/host/AzureDevOpsHostAdapter.ts").read_text()
        self.assertNotIn("azure-devops-extension-sdk", app_source)
        self.assertIn("azure-devops-extension-sdk", host_source)
        for value in ("organization", "project", "team", "sprint", "user", "theme", "extension", "route"):
            self.assertIn(value, host_source)

    def test_standalone_host_implements_the_same_contract(self):
        source = (EXTENSION / "src/host/StandaloneHostAdapter.ts").read_text()
        self.assertIn("implements HEIHostAdapter", source)
        self.assertIn("hostType: this.kind", source)
        self.assertIn("window.history.pushState", source)

    def test_work_item_action_deep_links_to_the_single_hub(self):
        source = (EXTENSION / "src/openHeiAction.ts").read_text()
        self.assertIn("AiIntelliCodegen.hei-engineering-platform.hei-command-center", source)
        self.assertIn("workItemId", source)
        self.assertIn("view: 'planning'", source)
        self.assertIn("HostNavigationService", source)

    def test_requirement_intake_uses_context_pipeline_and_requires_approval(self):
        result = self.service.submit(self.request())
        self.assertEqual("NeedsReview", result["status"])
        self.assertTrue(result["approvalRequired"])
        self.assertEqual("Planning", self.context.requests[0].purpose)
        self.assertTrue(self.context.requests[0].options["includeRepository"])
        self.assertTrue(self.context.requests[0].options["includeKnowledge"])
        self.assertTrue(self.context.requests[0].options["includeMemory"])
        self.assertEqual("PlanningPack", self.artifacts[0]["artifact_type"])
        self.assertEqual("draft", self.artifacts[0]["state"])
        self.assertEqual([], self.artifacts[0]["payload"]["recommendedHierarchy"]["features"])

    def test_requirement_intake_does_not_write_to_azure_devops(self):
        result = self.service.submit(self.request())
        self.assertNotIn("externalWorkItemId", result)
        self.assertEqual("Pending", self.artifacts[0]["payload"]["approval"]["status"])
        self.assertIn("before any Azure DevOps changes", self.artifacts[0]["payload"]["approval"]["message"])

    def test_requirement_intake_api_validates_and_returns_planning_pack(self):
        app = FastAPI(); app.include_router(build_requirement_intake_router(self.service)); client = TestClient(app)
        response = client.post("/requirements/intake", json=self.request())
        self.assertEqual(200, response.status_code)
        self.assertEqual("pack-1", response.json()["planningPackId"])
        invalid = client.post("/requirements/intake", json={"projectId": "project-1", "title": "Missing content"})
        self.assertEqual(400, invalid.status_code)
        self.assertEqual("invalid_requirement", invalid.json()["error"]["code"])

    def test_theme_and_diagnostics_contracts_are_present(self):
        host = (EXTENSION / "src/host/HostAdapter.ts").read_text()
        app = (EXTENSION / "src/heiApp.tsx").read_text()
        css = (EXTENSION / "src/storyPlanner.css").read_text()
        self.assertIn("high-contrast", host)
        self.assertIn("recordDiagnostic", app)
        self.assertIn("HubLoaded", app)
        self.assertIn("WorkspaceLoaded", app)
        self.assertIn("HubError", app)
        self.assertIn("Navigation", app)
        self.assertIn("data-hei-theme='high-contrast'", css)


if __name__ == "__main__":
    unittest.main()
