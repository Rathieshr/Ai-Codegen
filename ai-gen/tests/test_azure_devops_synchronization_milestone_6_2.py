from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.integrations.azure_devops import build_azure_devops_router
from backend.integrations.azure_devops.bootstrap import register_azure_devops_integration
from backend.integrations.azure_devops.domain import AzureDevOpsRateLimitError
from backend.platform import PlatformFoundation


def raw_work_item(item_id=11, revision=1, changed="2026-07-01T10:00:00+00:00", title="Device Health"):
    return {
        "id": item_id, "rev": revision, "url": f"https://ado/items/{item_id}",
        "fields": {
            "System.WorkItemType": "User Story", "System.Title": title,
            "System.State": "Active", "System.TeamProject": "GridHub",
            "System.ChangedDate": changed,
        },
        "relations": [{"rel": "System.LinkTypes.Hierarchy-Forward", "url": "https://ado/items/12"}],
    }


class SyncClient:
    def __init__(self):
        self.work_items = [raw_work_item()]
        self.wiql_calls = []
        self.fail_query_count = 0
        self.fail_builds = False
        self.pull_request_status = "active"

    def list_projects(self, **kwargs): return [{"id": "p1", "name": "GridHub"}]
    def get_project(self, project_id, **kwargs): return {"id": project_id, "name": "GridHub"}
    def list_teams(self, project_id, **kwargs): return [{"id": "t1", "name": "Platform", "projectId": project_id}]
    def list_iterations(self, project, **kwargs): return [{"id": "i1", "name": "Sprint 1", "path": "GridHub\\Sprint 1"}]

    def query_work_items(self, project, wiql, **kwargs):
        self.wiql_calls.append(wiql)
        if self.fail_query_count:
            self.fail_query_count -= 1
            raise AzureDevOpsRateLimitError("rate limited")
        if "[System.ChangedDate] >" in wiql:
            cursor = wiql.split("[System.ChangedDate] > '", 1)[1].split("'", 1)[0]
            return [item for item in self.work_items if item["fields"]["System.ChangedDate"] > cursor]
        return list(self.work_items)

    def get_work_item(self, project, work_item_id, **kwargs):
        return next((item for item in self.work_items if item["id"] == work_item_id), raw_work_item(work_item_id))

    def get_work_item_revisions(self, project, work_item_id, **kwargs):
        return [self.get_work_item(project, work_item_id)]

    def list_repositories(self, project, **kwargs):
        return [{"id": "r1", "name": "GridHub.API", "defaultBranch": "refs/heads/main", "project": {"id": "p1", "name": "GridHub"}}]

    def get_repository(self, project, repository_id, **kwargs): return self.list_repositories(project)[0]

    def list_pull_requests(self, project, repository_id="", **kwargs):
        return [{"pullRequestId": 21, "title": "Device Health", "status": self.pull_request_status, "repository": {"id": "r1"}}]

    def get_pull_request(self, project, repository_id, pull_request_id, **kwargs):
        return self.list_pull_requests(project, repository_id)[0]

    def list_builds(self, project, **kwargs):
        if self.fail_builds:
            raise RuntimeError("build endpoint unavailable")
        return [{"id": 31, "buildNumber": "20260713.1", "status": "completed", "result": "succeeded"}]


class Factory:
    def __init__(self, client): self.client = client
    def create(self, connection, *, correlation_id=""): return self.client


class AzureDevOpsSynchronizationMilestone62Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.client = SyncClient()
        self.module = register_azure_devops_integration(self.root / "ado", platform=self.platform, client_factory=Factory(self.client))
        self.connection = self.module.connections.register({
            "connectionId": "ado-1", "organizationUrl": "https://dev.azure.com/hei",
            "projectId": "p1", "authenticationMode": "PAT", "secretReference": "ADO_PAT",
        })

    def tearDown(self): self.temp.cleanup()

    def run_sync(self, sync_type="InitialFullSync"):
        requested = self.module.sync.request_sync("ado-1", "p1", sync_type, correlation_id="corr-sync")
        result = self.platform.job_runner.run_next()
        self.assertTrue(result["success"], result)
        return requested, self.module.sync.status("p1")

    def test_initial_sync_populates_all_normalized_collections_and_mappings(self):
        _, status = self.run_sync()
        counts = status["collectionCounts"]
        for name in ("projects", "teams", "iterations", "workItems", "workItemHierarchy", "workItemRevisions", "repositories", "pullRequests", "builds"):
            self.assertGreaterEqual(counts[name], 1, name)
        mappings = self.module.sync.mappings.list("p1")
        self.assertEqual({"project", "artifact", "repository"}, {item["mappingType"] for item in mappings})

    def test_incremental_sync_uses_cursor_and_reads_only_changed_work_items(self):
        self.run_sync()
        self.client.work_items.append(raw_work_item(12, 1, "2026-07-02T10:00:00+00:00", "Offline Devices"))
        self.run_sync("IncrementalSync")
        self.assertIn("[System.ChangedDate] >", self.client.wiql_calls[-1])
        self.assertEqual(2, len(self.module.sync.cache.collection("p1", "workItems")))

    def test_duplicate_webhook_delivery_is_idempotent(self):
        payload = {"id": "evt-1", "connectionId": "ado-1", "projectId": "p1", "eventType": "workitem.updated", "resource": {"id": 11}}
        first = self.module.sync.receive_webhook(payload, correlation_id="corr-webhook")
        second = self.module.sync.receive_webhook(payload, correlation_id="corr-webhook")
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["sync"]["syncId"], second["syncId"])
        queued = [job for job in self.platform.jobs.list_recent(20)["jobs"] if job["jobType"] == "AzureDevOpsWebhookSync"]
        self.assertEqual(1, len(queued))

    def test_out_of_order_webhook_does_not_replace_newer_work_item(self):
        self.run_sync()
        newer = raw_work_item(11, 5, "2026-07-05T10:00:00+00:00", "Current title")
        self.module.sync.cache.upsert("p1", "workItems", "11", self.module.work_items.get_hierarchy("ado-1", "p1", 11), revision_field="revision")
        self.module.sync.cache.upsert("p1", "workItems", "11", {**self.module.sync.cache.collection("p1", "workItems")["11"], "revision": 5, "title": "Current title"}, revision_field="revision")
        self.client.work_items = [raw_work_item(11, 2, "2026-07-02T10:00:00+00:00", "Old title")]
        payload = {"id": "evt-old", "connectionId": "ado-1", "projectId": "p1", "eventType": "workitem.updated", "resource": {"id": 11}}
        self.module.sync.receive_webhook(payload)
        self.platform.job_runner.run_next()
        self.assertEqual("Current title", self.module.sync.cache.collection("p1", "workItems")["11"]["title"])

    def test_deleted_work_item_removes_cached_record_and_details(self):
        self.run_sync()
        payload = {"id": "evt-delete", "connectionId": "ado-1", "projectId": "p1", "eventType": "workitem.deleted", "resource": {"id": 11}}
        self.module.sync.receive_webhook(payload)
        self.platform.job_runner.run_next()
        self.assertNotIn("11", self.module.sync.cache.collection("p1", "workItems"))
        self.assertNotIn("11", self.module.sync.cache.collection("p1", "workItemHierarchy"))
        self.assertEqual("WebhookSync", self.module.sync.status("p1")["latestSync"]["syncType"])

    def test_work_item_hierarchy_and_revisions_are_persisted(self):
        self.run_sync()
        hierarchy = self.module.sync.cache.collection("p1", "workItemHierarchy")["11"]
        revisions = self.module.sync.cache.collection("p1", "workItemRevisions")["11"]
        self.assertEqual("12", hierarchy["links"][0]["targetId"])
        self.assertEqual(1, len(revisions["revisions"]))

    def test_pull_request_merged_webhook_updates_cached_status(self):
        self.run_sync()
        self.client.pull_request_status = "completed"
        payload = {"id": "evt-pr", "connectionId": "ado-1", "projectId": "p1", "eventType": "git.pullrequest.merged", "resource": {"pullRequestId": 21, "repository": {"id": "r1"}}}
        self.module.sync.receive_webhook(payload)
        self.platform.job_runner.run_next()
        self.assertEqual("completed", self.module.sync.cache.collection("p1", "pullRequests")["21"]["status"])

    def test_reconciliation_is_incremental_when_cache_is_consistent(self):
        self.run_sync()
        self.run_sync("ScheduledReconciliation")
        self.assertIn("[System.ChangedDate] >", self.client.wiql_calls[-1])
        events = self.platform.events.list_recent("AzureDevOpsReconciliationRequired")["events"]
        self.assertEqual([], events)

    def test_reconciliation_repairs_missing_core_collection_with_full_sync(self):
        self.run_sync()
        self.module.sync.cache.replace("p1", "repositories", {})
        self.run_sync("ScheduledReconciliation")
        self.assertNotIn("[System.ChangedDate] >", self.client.wiql_calls[-1])
        self.assertEqual(1, len(self.module.sync.cache.collection("p1", "repositories")))

    def test_daily_scheduler_queues_due_reconciliation_once(self):
        self.run_sync()
        due = self.module.reconciliation_scheduler.run_due(now=datetime.now(timezone.utc) + timedelta(hours=25))
        self.assertEqual(1, len(due))
        duplicate = self.module.reconciliation_scheduler.run_due(now=datetime.now(timezone.utc) + timedelta(hours=25))
        self.assertEqual([], duplicate)

    def test_partial_section_failure_preserves_successful_data(self):
        self.client.fail_builds = True
        _, status = self.run_sync()
        self.assertEqual("Partial", status["latestSync"]["status"])
        self.assertIn("builds:", status["latestSync"]["warnings"][0])
        self.assertEqual(1, status["collectionCounts"]["workItems"])

    def test_platform_job_retries_transient_sync_failure(self):
        self.client.fail_query_count = 1
        self.module.sync.request_sync("ado-1", "p1", "InitialFullSync", correlation_id="corr-retry")
        first = self.platform.job_runner.run_next()
        self.assertFalse(first["success"])
        self.assertEqual("Queued", first["status"])
        second = self.platform.job_runner.run_next()
        self.assertTrue(second["success"])
        self.assertEqual("Completed", self.module.sync.status("p1")["latestSync"]["status"])

    def test_sync_api_exposes_status_history_webhook_and_reconcile(self):
        app = FastAPI()
        app.include_router(build_azure_devops_router(self.module))
        api = TestClient(app)
        response = api.post("/integrations/azure-devops/projects/p1/sync", json={"connectionId": "ado-1", "syncType": "InitialFullSync"})
        self.assertEqual(202, response.status_code)
        self.platform.job_runner.run_next()
        self.assertEqual(200, api.get("/integrations/azure-devops/projects/p1/sync-status").status_code)
        self.assertEqual(1, api.get("/integrations/azure-devops/projects/p1/sync-history").json()["count"])
        webhook = api.post("/integrations/azure-devops/webhooks", json={"id": "api-event", "connectionId": "ado-1", "projectId": "p1", "eventType": "git.push", "resource": {}})
        self.assertEqual(202, webhook.status_code)
        reconcile = api.post("/integrations/azure-devops/projects/p1/reconcile", json={"connectionId": "ado-1"})
        self.assertEqual(202, reconcile.status_code)


if __name__ == "__main__":
    unittest.main()
