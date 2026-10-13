from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_work_item_import import AzureDevOpsWorkItemImportService, build_ado_work_item_import_router
from backend.integrations.azure_devops.mapping import map_work_item
from backend.integrations.azure_devops.domain import AzureDevOpsConnection
from backend.integrations.azure_devops.infrastructure import AzureDevOpsReadClient, HttpResponse
from backend.platform.shared import JsonMapStore
from backend.platform_sdk import HEIAzureDevOpsSdk
from backend.requirement_intake import RequirementIngestionService


def story(**overrides):
    value = {
        "workItemId": 245,
        "workItemType": "User Story",
        "title": "View Offline Devices",
        "description": "Operations users need to identify disconnected devices before outage investigation begins.",
        "acceptanceCriteria": ["Offline devices are visible", "Results can be filtered by feeder"],
        "comments": [{"commentId": "7", "text": "Confirm the stale threshold.", "createdBy": "Maya", "createdAt": "2026-07-20"}],
        "attachments": [{"name": "device-health.png", "url": "https://ado/attachment/1", "comment": "Reference"}],
        "links": [{"relation": "System.LinkTypes.Dependency-Forward", "targetId": "88", "targetUrl": "https://ado/items/88"}],
        "areaPath": "GridHub\\Operations",
        "iterationPath": "GridHub\\Sprint 4",
        "tags": ["Device Health", "Operations"],
        "state": "New",
        "revision": 4,
        "projectName": "GridHub",
    }
    value.update(overrides)
    return value


class Cache:
    def __init__(self):
        self.values = {"p1": {"workItems": {"245": story()}}}

    def find(self, collection, key, project_id=""):
        projects = [project_id] if project_id else list(self.values)
        for project in projects:
            value = self.values.get(project, {}).get(collection, {}).get(str(key))
            if value:
                return project, value
        return None

    def collection(self, project_id, collection):
        return self.values.get(project_id, {}).get(collection, {})

    def snapshot(self, project_id):
        return self.values.get(project_id, {})

    def upsert(self, project_id, collection, key, value, **kwargs):
        self.values.setdefault(project_id, {}).setdefault(collection, {})[str(key)] = value
        return "updated"


class WorkItems:
    def __init__(self, cache): self.cache = cache
    def get_details(self, connection_id, project_id, work_item_id, **kwargs): return dict(self.cache.values[project_id]["workItems"][str(work_item_id)])


class Credentials:
    def authorization_headers(self, connection, correlation_id=""): return {"Authorization": "Basic redacted"}


class Executor:
    def __init__(self, payload): self.payload = payload
    def execute(self, method, url, headers, body, timeout, cancellation=None): return HttpResponse(200, {}, self.payload)


class AzureDevOpsWorkItemImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.cache = Cache()
        integration = SimpleNamespace(sync=SimpleNamespace(cache=self.cache), work_items=WorkItems(self.cache))
        self.sdk = HEIAzureDevOpsSdk(integration)
        self.requirements = RequirementIngestionService(
            JsonMapStore(root / "requirements.json"),
            work_item_provider=lambda project_id, work_item_id: (found := self.sdk.find_cached("workItems", work_item_id, project_id)) and dict(found[1]),
        )
        self.service = AzureDevOpsWorkItemImportService(
            JsonMapStore(root / "imports.json"),
            azure_devops=self.sdk,
            requirement_ingestion=self.requirements,
        )

    def tearDown(self): self.temp.cleanup()

    def test_get_returns_complete_normalized_work_item(self):
        result = self.service.get("245", project_id="p1")
        self.assertEqual("User Story", result["workItemType"])
        self.assertEqual(2, len(result["acceptanceCriteria"]))
        self.assertEqual("Maya", result["comments"][0]["createdBy"])
        self.assertEqual("device-health.png", result["attachments"][0]["name"])
        self.assertEqual("GridHub\\Operations", result["area"])
        self.assertEqual("GridHub\\Sprint 4", result["iteration"])
        self.assertEqual(["Device Health", "Operations"], result["tags"])
        self.assertTrue(result["linkedWorkItems"][0]["isDependency"])

    def test_analyze_creates_requirement_summary_before_planning_context(self):
        result = self.service.analyze("245", {"projectId": "p1", "actor": "Maya"}, correlation_id="corr-import")
        self.assertEqual("Ready", result["status"])
        self.assertTrue(result["requirementSummary"]["readyForPlanning"])
        self.assertEqual("88", result["requirementSummary"]["dependencies"][0]["workItemId"])
        context = self.requirements.get(result["requirementContextId"])
        self.assertIn("Requirement Summary", context["normalizedRequirement"])
        self.assertIn("Dependencies", context["normalizedRequirement"])
        self.assertEqual("AzureDevOpsWorkItem", context["sourceType"])

    def test_missing_information_blocks_planning_context(self):
        self.cache.values["p1"]["workItems"]["245"] = story(description="Short", acceptanceCriteria=[])
        result = self.service.analyze("245", {"projectId": "p1"})
        self.assertEqual("NeedsReview", result["status"])
        self.assertFalse(result["requirementSummary"]["readyForPlanning"])
        self.assertEqual("", result["requirementContextId"])
        self.assertEqual(2, len(result["requirementSummary"]["missingInformation"]))

    def test_all_supported_work_item_types_can_be_imported(self):
        for index, item_type in enumerate(("Epic", "Feature", "Story", "User Story", "Task", "Bug"), start=1):
            item = story(workItemId=index, workItemType=item_type)
            if item_type == "Bug":
                item["description"] = "Steps to reproduce the fault. Actual status is online; expected status is offline."
            self.cache.values["p1"]["workItems"][str(index)] = item
            self.assertEqual(item_type, self.service.get(str(index), project_id="p1")["workItemType"])

    def test_unsupported_type_is_rejected_during_analysis(self):
        self.cache.values["p1"]["workItems"]["9"] = story(workItemId=9, workItemType="Test Case")
        with self.assertRaises(ValueError):
            self.service.analyze("9", {"projectId": "p1"})

    def test_mapper_normalizes_comments_and_attachment_relations(self):
        mapped = map_work_item({
            "id": 4,
            "rev": 2,
            "fields": {"System.WorkItemType": "Task", "System.Title": "Update API"},
            "comments": [{"id": 3, "text": "Use v2", "createdBy": {"displayName": "Alex"}}],
            "relations": [{"rel": "AttachedFile", "url": "https://ado/a/1", "attributes": {"name": "contract.json"}}],
        })
        self.assertEqual("Alex", mapped.comments[0]["createdBy"])
        self.assertEqual("contract.json", mapped.attachments[0]["name"])

    def test_read_client_supports_ado_comments_response_shape(self):
        connection = AzureDevOpsConnection.create({"organizationUrl": "https://dev.azure.com/hei", "secretReference": "ADO_PAT"})
        client = AzureDevOpsReadClient(connection, Credentials(), executor=Executor({"comments": [{"id": 1, "text": "Confirm access rules"}]}))
        self.assertEqual("Confirm access rules", client.get_work_item_comments("GridHub", 245)[0]["text"])

    def test_exact_api_contracts(self):
        app = FastAPI()
        app.include_router(build_ado_work_item_import_router(self.service))
        client = TestClient(app)
        current = client.get("/ado/workitem/245", params={"projectId": "p1"})
        self.assertEqual(200, current.status_code)
        analyzed = client.post("/ado/workitem/245/analyze", json={"projectId": "p1"})
        self.assertEqual(200, analyzed.status_code)
        self.assertTrue(analyzed.json()["requirementSummary"]["readyForPlanning"])
        self.assertEqual(404, client.get("/ado/workitem/999", params={"projectId": "p1"}).status_code)


if __name__ == "__main__":
    unittest.main()
