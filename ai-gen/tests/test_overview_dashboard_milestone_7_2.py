from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.dashboard import DashboardService, build_dashboard_router
from backend.platform import PlatformFoundation


class Stub:
    def __init__(self, **values):
        self.__dict__.update(values)


class RepositorySource:
    def __init__(self, count=0):
        self.count = count

    def get_repository_monitoring_dashboard(self):
        return {
            "repositoryCount": self.count, "healthyCount": self.count, "pendingCount": 0,
            "unhealthyCount": 0, "filesIndexed": self.count * 100, "modulesIndexed": self.count * 5,
            "pendingScanCount": 0, "health": "Healthy" if self.count else "Pending",
            "repositories": [{"repositoryId": f"repo-{index}", "repositoryName": f"Repository {index}", "health": "Healthy"} for index in range(self.count)],
        }


class SyncSource:
    def __init__(self, builds=0, pull_requests=0, iterations=None):
        self.builds, self.pull_requests = builds, pull_requests
        self.iterations = iterations or {}
        self.cache = Stub(snapshot=self.snapshot)

    def status(self, project_id):
        return {"projectId": project_id, "latestSync": {"status": "Completed"}, "collectionCounts": {"builds": self.builds, "pullRequests": self.pull_requests}}

    def snapshot(self, project_id):
        return {
            "builds": {str(index): {"buildId": index, "status": "completed", "result": "succeeded"} for index in range(self.builds)},
            "pullRequests": {str(index): {"pullRequestId": index, "status": "active"} for index in range(self.pull_requests)},
            "iterations": self.iterations,
        }


class FailingSource:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError(f"{name} is offline")
        return fail


class OverviewDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.platform = PlatformFoundation(Path(self.temp.name) / "platform")

    def tearDown(self):
        self.temp.cleanup()

    def service(self, *, profile=None, repositories=None, sync=None, sprint=None, agents=None, governance=None, runtime=None, memory=None, artifacts=None):
        return DashboardService(
            platform=self.platform,
            profile_provider=lambda: profile or {},
            repository_service=repositories,
            ado_sync=sync,
            sprint_service=sprint,
            agent_service=agents,
            governance_service=governance,
            runtime_service=runtime,
            memory_candidate_service=memory,
            artifact_provider=(lambda: artifacts or {"artifacts": [], "count": 0}),
        )

    def test_empty_workspace_is_explainable(self):
        value = self.service().overview()
        self.assertEqual("Empty", value["status"])
        self.assertFalse(value["currentProject"]["configured"])
        self.assertEqual(0, value["repositoryStatus"]["repositoryCount"])
        self.assertEqual("Not Available", value["buildStatus"]["status"])

    def test_multiple_repositories_and_operational_widgets(self):
        value = self.service(profile={"project_id": "p1", "project_name": "GridHub"}, repositories=RepositorySource(3), sync=SyncSource(2, 4)).overview()
        self.assertEqual(3, value["repositoryStatus"]["repositoryCount"])
        self.assertEqual(300, value["repositoryStatus"]["filesIndexed"])
        self.assertEqual(4, value["prIntelligence"]["pullRequestCount"])
        self.assertEqual(["Repository", "Planning", "Execution", "Azure DevOps", "Approvals", "Runtime", "Agents", "Health", "Recent Activity"], [item["title"] for item in value["widgets"]])

    def test_large_project_caps_widget_detail_without_losing_totals(self):
        traces = [{"traceId": f"trace-{index}", "status": "Completed"} for index in range(1500)]
        candidates = [{"candidateId": f"candidate-{index}", "approvalStatus": "Pending", "projectScope": {"projectId": "large"}} for index in range(1200)]
        service = self.service(
            profile={"project_id": "large", "project_name": "Large Project"}, repositories=RepositorySource(80),
            runtime=Stub(list=lambda limit=100: {"traces": traces[:limit], "count": len(traces)}),
            memory=Stub(list=lambda project_id="": {"candidates": candidates, "count": len(candidates)}),
        )
        value = service.overview("large")
        self.assertEqual(80, value["repositoryStatus"]["repositoryCount"])
        self.assertLessEqual(len(value["repositoryStatus"]["repositories"]), 50)
        self.assertEqual(1500, value["executionQueue"]["total"])
        self.assertLessEqual(len(value["executionQueue"]["recent"]), 8)
        self.assertEqual(1200, value["memoryCandidates"]["count"])
        self.assertLessEqual(len(value["memoryCandidates"]["items"]), 8)

    def test_no_azure_devops_is_not_connected_without_failure(self):
        value = self.service(profile={"project_id": "p1", "project_name": "Local Project"}, repositories=RepositorySource(1)).overview()
        self.assertFalse(value["azureDevOps"]["connected"])
        self.assertEqual("NotConnected", value["repositorySync"]["status"])
        self.assertTrue(any(item["source"] == "azureDevOps" and item["code"] == "not_configured" for item in value["warnings"]))

    def test_overview_reads_cached_sprint_without_running_intelligence(self):
        class SprintSource:
            def __init__(self):
                self.current_calls = 0
                self.repository = Stub(get=lambda project_id, iteration_id: {"projectId": project_id, "iterationId": iteration_id, "health": "Ready", "iteration": {"name": "Sprint 14"}})

            def current(self, project_id):
                self.current_calls += 1
                raise AssertionError("Overview must not generate sprint intelligence.")

        sprint = SprintSource()
        sync = SyncSource(iterations={"14": {"iterationId": "14", "name": "Sprint 14", "timeFrame": "current"}})
        value = self.service(profile={"project_id": "p1", "project_name": "GridHub"}, sync=sync, sprint=sprint).overview()
        self.assertEqual("Ready", value["currentSprint"]["health"])
        self.assertEqual(0, sprint.current_calls)

    def test_offline_sources_degrade_independently(self):
        failing = FailingSource()
        value = self.service(
            profile={"project_id": "p1", "project_name": "Offline Project"}, repositories=failing,
            sync=failing, sprint=failing, agents=failing, governance=failing, runtime=failing, memory=failing,
        ).overview()
        self.assertEqual("Offline", value["status"])
        self.assertEqual("Degraded", value["health"]["status"])
        self.assertGreaterEqual(len([item for item in value["warnings"] if item["code"] == "unavailable"]), 6)

    def test_summary_and_api_contract(self):
        service = self.service(profile={"project_id": "p1", "project_name": "GridHub"}, repositories=RepositorySource(2), sync=SyncSource(1, 1))
        app = FastAPI(); app.include_router(build_dashboard_router(service)); client = TestClient(app)
        overview = client.get("/dashboard/overview?projectId=p1")
        self.assertEqual(200, overview.status_code)
        self.assertEqual("hei-dashboard-overview-v1", overview.json()["schemaVersion"])
        self.assertEqual(9, client.get("/dashboard/widgets?projectId=p1").json()["count"])
        self.assertEqual(2, client.get("/dashboard/summary?projectId=p1").json()["repositories"])


if __name__ == "__main__":
    unittest.main()
