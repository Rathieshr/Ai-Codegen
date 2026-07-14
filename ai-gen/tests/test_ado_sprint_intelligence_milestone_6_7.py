from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_intelligence.api import build_ado_intelligence_router
from backend.ado_intelligence.sprint_repository import SprintIntelligenceRepository
from backend.ado_intelligence.sprint_service import SprintIntelligenceService
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


class Cache:
    def __init__(self):
        self.values = {}

    def collection(self, project_id, name):
        return self.values.get((project_id, name), {})

    def put(self, project_id, name, key, value):
        self.values.setdefault((project_id, name), {})[str(key)] = value


class Estimation:
    def __init__(self, calibrated=True):
        self.calibrated = calibrated

    def accuracy(self, project_id, team_id="", include_items=False):
        return {
            "projectId": project_id, "teamId": team_id,
            "calibrationScope": "Project" if self.calibrated else "Uncalibrated",
            "sampleCount": 5 if self.calibrated else 0,
            "accuracy": 84.0 if self.calibrated else None,
            "bias": "Balanced" if self.calibrated else "Insufficient history",
        }


class SprintIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.cache = Cache()
        self.platform = PlatformFoundation(root / "platform")
        self.estimation = Estimation()
        self.service = SprintIntelligenceService(
            azure_devops=SimpleNamespace(sync=SimpleNamespace(cache=self.cache)),
            repository=SprintIntelligenceRepository(JsonMapStore(root / "sprint_reports.json")),
            estimation=self.estimation, platform=self.platform,
            clock=lambda: datetime(2026, 7, 7, 12, tzinfo=timezone.utc),
        )
        self.iteration = {
            "iterationId": "sprint-7", "name": "Sprint 7", "path": "GridHub\\Sprint 7",
            "startDate": "2026-07-01T00:00:00Z", "finishDate": "2026-07-14T23:59:59Z", "timeFrame": "current",
        }
        self.cache.put("project-1", "iterations", "sprint-7", self.iteration)
        self.put_item("1", "Fault details", "Closed", 3, closed="2026-07-04T12:00:00Z")
        self.put_item("2", "Permission handling", "Closed", 2, closed="2026-07-06T12:00:00Z")
        self.put_item("3", "Device status", "Active", 3)
        self.put_item("4", "Regression coverage", "New", 2)
        self.cache.put("project-1", "pullRequests", "11", {"pullRequestId": 11, "status": "active", "creationDate": "2026-07-06T10:00:00Z", "linkedWorkItemIds": ["3"]})
        self.cache.put("project-1", "builds", "21", {"buildId": 21, "status": "completed", "result": "succeeded", "finishTime": "2026-07-06T18:00:00Z"})

    def tearDown(self):
        self.temp.cleanup()

    def put_item(self, item_id, title, state, points=None, *, created="2026-07-01T09:00:00Z", changed="2026-07-06T09:00:00Z", closed="", work_type="User Story", tags=None, links=None, path="GridHub\\Sprint 7"):
        self.cache.put("project-1", "workItems", item_id, {
            "workItemId": item_id, "workItemType": work_type, "title": title, "state": state,
            "iterationPath": path, "storyPoints": points, "createdAt": created, "changedAt": changed,
            "closedAt": closed, "tags": tags or [], "links": links or [], "revision": 1,
        })

    def test_healthy_sprint_reports_flow_metrics_and_forecast(self):
        report = self.service.current("project-1")
        self.assertEqual("Healthy", report["health"])
        self.assertEqual(10, report["metrics"]["plannedScope"]["storyPoints"])
        self.assertEqual(5, report["metrics"]["completedScope"]["storyPoints"])
        self.assertEqual("OnTrack", report["forecast"]["status"])
        self.assertTrue(report["burndownSeries"])
        self.assertEqual("NotEvaluated", report["metrics"]["capacity"]["status"])
        self.assertFalse(report["privacy"]["individualRanking"])
        self.assertNotIn("assignedTo", str(report))

    def test_scope_increase_detects_late_addition(self):
        self.service.clock = lambda: datetime(2026, 7, 12, 12, tzinfo=timezone.utc)
        self.put_item("5", "Late alert change", "New", 3, created="2026-07-10T09:00:00Z")
        report = self.service.report("project-1", "sprint-7")
        self.assertIn("LateScopeAddition", self.signals(report))

    def test_scope_increase_uses_revision_that_entered_sprint(self):
        self.service.clock = lambda: datetime(2026, 7, 12, 12, tzinfo=timezone.utc)
        self.put_item("5", "Existing backlog item", "New", 3, created="2026-06-01T09:00:00Z")
        self.cache.put("project-1", "workItemRevisions", "5", {"revisions": [
            {"iterationPath": "GridHub\\Backlog", "changedAt": "2026-06-01T09:00:00Z"},
            {"iterationPath": "GridHub\\Sprint 7", "changedAt": "2026-07-10T09:00:00Z"},
        ]})
        report = self.service.report("project-1", "sprint-7")
        self.assertIn("LateScopeAddition", self.signals(report))
        self.assertNotIn("5", report["metrics"]["carryover"]["workItemIds"])

    def test_blocked_dependency_is_a_current_blocker(self):
        self.put_item("5", "Blocked integration", "Blocked", 3, tags=["Blocked"], links=[{"relation": "System.LinkTypes.Dependency-Forward", "targetId": "88"}])
        report = self.service.report("project-1", "sprint-7")
        self.assertIn("BlockedDependency", self.signals(report))
        self.assertEqual("5", report["currentBlockers"][0]["workItemId"])

    def test_pr_review_bottleneck_uses_waiting_time(self):
        self.cache.put("project-1", "pullRequests", "11", {"pullRequestId": 11, "status": "active", "creationDate": "2026-07-01T10:00:00Z", "linkedWorkItemIds": ["3"]})
        report = self.service.report("project-1", "sprint-7")
        self.assertIn("PullRequestReviewBottleneck", self.signals(report))
        self.assertEqual(6.1, report["metrics"]["pullRequestWaitingTime"]["maximumWaitingDays"])

    def test_repeated_build_failures_are_reported(self):
        self.cache.put("project-1", "builds", "22", {"buildId": 22, "result": "failed", "finishTime": "2026-07-05T18:00:00Z"})
        self.cache.put("project-1", "builds", "23", {"buildId": 23, "result": "failed", "finishTime": "2026-07-06T18:00:00Z"})
        report = self.service.report("project-1", "sprint-7")
        self.assertIn("RepeatedBuildFailures", self.signals(report))
        self.assertEqual(2, report["metrics"]["buildFailures"]["failedCount"])

    def test_stale_capacity_and_high_risk_signals_are_explainable(self):
        self.iteration["capacityStoryPoints"] = 8
        self.put_item("5", "Security permission task", "Active", 3, changed="2026-06-25T09:00:00Z", work_type="Task", tags=["Security"])
        report = self.service.report("project-1", "sprint-7")
        self.assertTrue({"StaleTask", "CapacityMismatch", "HighRiskUntestedWork"}.issubset(self.signals(report)))
        self.assertEqual("Exceeded", report["metrics"]["capacity"]["status"])

    def test_wip_and_large_unfinished_story_signals(self):
        self.cache.collection("project-1", "workItems")["3"]["storyPoints"] = 8
        for index in range(5, 10):
            self.put_item(str(index), f"Active task {index}", "Active", 1, work_type="Task")
        report = self.service.report("project-1", "sprint-7")
        self.assertTrue({"TooMuchWorkInProgress", "LargeUnfinishedStory"}.issubset(self.signals(report)))

    def test_missing_estimates_reduce_confidence_without_fake_precision(self):
        for item in self.cache.collection("project-1", "workItems").values():
            item["storyPoints"] = None
        report = self.service.report("project-1", "sprint-7")
        self.assertEqual(4, report["metrics"]["plannedScope"]["unestimatedItemCount"])
        self.assertIn("Many sprint items do not have estimates.", report["completionConfidence"]["reasons"])
        self.assertLess(report["completionConfidence"]["score"], 80)

    def test_sparse_history_is_explicit(self):
        self.service.estimation = Estimation(calibrated=False)
        report = self.service.report("project-1", "sprint-7")
        self.assertEqual("SparseHistory", report["metrics"]["velocity"]["status"])
        self.assertIsNone(report["metrics"]["estimateAccuracy"]["accuracy"])
        self.assertIn("Historical estimate calibration is sparse.", report["completionConfidence"]["reasons"])

    def test_carryover_is_identified_from_pre_sprint_creation(self):
        self.cache.collection("project-1", "workItems")["3"]["createdAt"] = "2026-06-25T09:00:00Z"
        report = self.service.report("project-1", "sprint-7")
        self.assertEqual(["3"], report["metrics"]["carryover"]["workItemIds"])

    def test_no_activity_returns_insufficient_data(self):
        self.cache.values[("project-1", "workItems")] = {}
        report = self.service.report("project-1", "sprint-7")
        self.assertEqual("InsufficientData", report["health"])
        self.assertEqual("InsufficientData", report["forecast"]["status"])
        self.assertEqual(20, report["completionConfidence"]["score"])

    def test_completed_sprint_is_reported_without_future_prediction(self):
        for item in self.cache.collection("project-1", "workItems").values():
            item["state"] = "Closed"
            item["closedAt"] = "2026-07-07T10:00:00Z"
        report = self.service.report("project-1", "sprint-7")
        self.assertEqual("Completed", report["health"])
        self.assertEqual("Completed", report["forecast"]["status"])
        self.assertEqual(0, report["metrics"]["remainingScope"]["itemCount"])

    def test_all_sprint_apis_return_explainable_views(self):
        wrapper = SimpleNamespace(sprints=self.service, estimation=None, pull_requests=None)
        app = FastAPI()
        app.include_router(build_ado_intelligence_router(wrapper))
        client = TestClient(app)
        paths = [
            "/ado-intelligence/projects/project-1/sprints/current",
            "/ado-intelligence/projects/project-1/sprints/sprint-7/report",
            "/ado-intelligence/projects/project-1/sprints/sprint-7/burndown",
            "/ado-intelligence/projects/project-1/sprints/sprint-7/risks",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(200, client.get(path).status_code)

    @staticmethod
    def signals(report):
        return {item["signal"] for item in report["deliveryRisks"]}


if __name__ == "__main__":
    unittest.main()
