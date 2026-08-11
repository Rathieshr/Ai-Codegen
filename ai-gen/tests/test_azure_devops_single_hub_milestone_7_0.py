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
        self.assertIn('logoSrc="../../static/hei-icon-light.png"', source)
        self.assertIn('logoDarkSrc="../../static/hei-icon-dark.png"', source)
        self.assertNotIn("window.location.reload", source)

    def test_hei_app_icon_switches_for_light_and_dark_themes(self):
        app = (EXTENSION / "src/heiApp.tsx").read_text()
        shell = (EXTENSION / "src/engineeringCommandCenterShell.tsx").read_text()
        styles = (EXTENSION / "src/storyPlanner.css").read_text()
        manifest = (EXTENSION / "azure-devops-extension.hei.json").read_text()
        self.assertTrue((EXTENSION / "static/hei-icon-light.png").is_file())
        self.assertTrue((EXTENSION / "static/hei-icon-dark.png").is_file())
        self.assertIn("hei-icon-light.png", app + shell + manifest)
        self.assertIn("hei-icon-dark.png", app + shell)
        self.assertIn("data-hei-theme='dark'", styles)
        self.assertIn("prefers-color-scheme: dark", styles)
        self.assertIn('"light": "static/hei-icon-light.png"', manifest)
        self.assertIn('"dark": "static/hei-icon-dark.png"', manifest)
        self.assertIn('"iconAsset": "AiIntelliCodegen.hei-engineering-platform/static/hei-icon-light.png"', manifest)
        self.assertIn('AiIntelliCodegen.hei-engineering-platform/static/hei-icon-dark.png', manifest)
        self.assertNotIn('"iconName": "EngineeringGroup"', manifest)

    def test_azure_devops_sdk_is_isolated_to_host_adapter(self):
        app_source = (EXTENSION / "src/heiApp.tsx").read_text()
        host_source = (EXTENSION / "src/host/AzureDevOpsHostAdapter.ts").read_text()
        self.assertNotIn("azure-devops-extension-sdk", app_source)
        self.assertIn("azure-devops-extension-sdk", host_source)
        for value in ("organization", "project", "team", "sprint", "user", "theme", "extension", "route"):
            self.assertIn(value, host_source)

    def test_hub_releases_azure_loader_before_context_resolution(self):
        host_source = (EXTENSION / "src/host/AzureDevOpsHostAdapter.ts").read_text()
        self.assertIn("withTimeout(this.initialization, 10000", host_source)
        self.assertIn("SDK.notifyLoadFailed", host_source)
        self.assertLess(host_source.index("SDK.notifyLoadSucceeded"), host_source.index("SDK.getWebContext"))

    def test_hub_renders_fallback_before_backend_hydration_and_can_retry(self):
        source = (EXTENSION / "src/heiApp.tsx").read_text()
        self.assertLess(source.index("setWorkspace(fallback)"), source.index("requestWorkspace(hostContext)"))
        self.assertIn("Retry HEI startup", source)
        self.assertIn("fetchWithTimeout", source)
        self.assertIn("WorkspaceFallback", source)

    def test_standalone_host_implements_the_same_contract(self):
        source = (EXTENSION / "src/host/StandaloneHostAdapter.ts").read_text()
        self.assertIn("implements HEIHostAdapter", source)
        self.assertIn("hostType: this.kind", source)
        self.assertIn("window.history.pushState", source)

    def test_missing_host_role_uses_safe_defaults(self):
        contract = (EXTENSION / "src/host/HostAdapter.ts").read_text()
        azure = (EXTENSION / "src/host/AzureDevOpsHostAdapter.ts").read_text()
        standalone = (EXTENSION / "src/host/StandaloneHostAdapter.ts").read_text()
        self.assertIn("String(value || '')", contract)
        self.assertIn("normalizeHostRole(route.role, 'admin')", azure)
        self.assertIn("normalizeHostRole(route.role, 'viewer')", standalone)
        self.assertNotIn("route.role.toLowerCase", azure + standalone)

    def test_azure_host_admin_fallback_exposes_administration(self):
        app = (EXTENSION / "src/heiApp.tsx").read_text()
        host = (EXTENSION / "src/host/AzureDevOpsHostAdapter.ts").read_text()
        self.assertIn("normalizeHostRole(route.role, 'admin')", host)
        self.assertIn("item('settings', 'Administration', 'settings')", app)

    def test_settings_restores_user_configurable_repository_mapping(self):
        settings = (EXTENSION / "src/settingsWorkspace.tsx").read_text()
        for label in ("Azure DevOps Project", "Repository", "Branch", "Save Repository Mapping"):
            self.assertIn(label, settings)
        self.assertIn("/project-intelligence/connectors/azure-devops/projects", settings)
        self.assertIn("/project-intelligence/connectors/azure-devops/repositories", settings)
        self.assertIn("/project-intelligence/connectors/azure-devops/branches", settings)
        self.assertIn("/project-intelligence/connectors/azure-devops/mapping", settings)
        self.assertIn("ensureRepositoryRegistration", settings)
        self.assertIn("`${baseUrl}/repositories`", settings)
        self.assertIn("repository.webUrl || repository.remoteUrl", settings)
        self.assertLess(settings.index("ensureRepositoryRegistration(baseUrl, next"), settings.index("/project-intelligence/connectors/azure-devops/mapping`"))

    def test_administration_center_exposes_enterprise_sections_and_live_controls(self):
        settings = (EXTENSION / "src/settingsWorkspace.tsx").read_text()
        for section in (
            "Azure DevOps", "Repositories", "Agents", "Integrations", "Platform",
            "Diagnostics", "Security", "Audit", "Host", "Feature Flags",
        ):
            self.assertIn(f"label: '{section}'", settings)
        for heading in ("Health", "Configuration", "Validation", "Diagnostics", "Last Updated"):
            self.assertIn(f">{heading}<", settings)
        self.assertIn("/project-intelligence/agents/policies", settings)
        self.assertIn("/project-intelligence/agents/flags", settings)
        self.assertIn("/command-center/diagnostics?role=admin", settings)
        self.assertIn("/audit/events?limit=50", settings)
        self.assertIn("Promise.allSettled", settings)
        self.assertIn("The credential reference names a secure backend environment variable", settings)

    def test_administration_connects_validates_and_synchronizes_azure_devops(self):
        settings = (EXTENSION / "src/settingsWorkspace.tsx").read_text()
        for label in (
            "Azure DevOps Connection",
            "Organization URL",
            "Credential Reference",
            "Connect Azure DevOps",
            "Validate Connection",
            "Synchronize Project",
        ):
            self.assertIn(label, settings)
        self.assertIn("/integrations/azure-devops/connections`", settings)
        self.assertIn("/integrations/azure-devops/connections/${encodeURIComponent(current.connectionId)}/validate", settings)
        self.assertIn("/integrations/azure-devops/projects/${encodeURIComponent(context.project.id || context.project.name)}/sync", settings)
        self.assertIn("secretReference: secretReference.trim() || 'ADO_PAT'", settings)
        self.assertIn("syncType: 'ManualSync'", settings)
        self.assertNotIn("type=\"password\"", settings)

    def test_rejected_azure_devops_connection_can_be_corrected_and_revalidated(self):
        settings = (EXTENSION / "src/settingsWorkspace.tsx").read_text()
        self.assertIn("'failed', 'rejected', 'degraded', 'pendingvalidation'", settings)
        self.assertIn("Save & Validate Connection", settings)
        self.assertIn("Update the rejected connection settings", settings)
        self.assertIn("'PUT'", settings)
        self.assertNotIn("disabled={connectionBusy || Boolean(connection)}", settings)

    def test_saved_mapping_drives_repository_center_and_overview_uses_host_project(self):
        app = (EXTENSION / "src/heiApp.tsx").read_text()
        overview = (EXTENSION / "src/overviewDashboard.tsx").read_text()
        self.assertIn("loadRepositoryConfiguration(hostContext)", app)
        self.assertIn("repositoryMapping?.intelligenceRepositoryId || context.repository.id", app)
        self.assertIn("onMappingChanged", app)
        self.assertIn("name: hostContext.project.name || value.currentProject.name", app)
        self.assertNotIn("Connect a project to load operational engineering state.", overview)
        self.assertIn("Configure a repository in Administration", overview)
        self.assertIn("Repository Intelligence", overview)
        self.assertIn("Azure DevOps Sync", overview)
        self.assertIn("Open Repository", overview)
        self.assertIn("repositoryName={repositoryMapping?.repository_name", app)

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
