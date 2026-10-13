from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_center import AzureDevOpsCenterService, build_ado_center_router


class Cache:
    def __init__(self, projects=None):
        self.projects = projects or {}

    def snapshot(self, project_id):
        return self.projects.get(project_id, {})


class Sync:
    def __init__(self, projects=None):
        self.cache = Cache(projects)

    def status(self, project_id):
        snapshot = self.cache.snapshot(project_id)
        return {
            "projectId": project_id,
            "latestSync": {"status": "Completed", "completedAt": "2026-07-14T10:00:00Z"} if snapshot else None,
            "collectionCounts": {key: len(value) for key, value in snapshot.items() if isinstance(value, dict)},
            "centralized": True,
            "sourceOfTruth": "Azure DevOps",
        }


class Sprint:
    def __init__(self, available=True):
        self.available = available

    def current(self, project_id, team_id=""):
        if not self.available:
            raise LookupError("No current sprint")
        return {
            "projectId": project_id,
            "iteration": {"iterationId": "sprint-14", "name": "Sprint 14"},
            "health": "AtRisk",
            "completionConfidence": {"score": 72, "level": "Medium"},
            "forecast": {"status": "AtRisk", "onTrack": False},
            "metrics": {
                "plannedScope": {"itemCount": 20, "storyPoints": 42},
                "completedScope": {"itemCount": 12, "storyPoints": 24},
                "remainingScope": {"itemCount": 8, "storyPoints": 18},
                "velocity": {"currentCompletedStoryPoints": 24, "historicalAverageStoryPoints": 27, "historicalSprintCount": 5, "status": "Calibrated"},
            },
            "burndownSeries": [{"date": "2026-07-13", "remainingItems": 10}, {"date": "2026-07-14", "remainingItems": 8}],
            "currentBlockers": [{"workItemId": "2", "title": "Blocked API"}],
            "deliveryRisks": [{"signal": "BlockedDependency", "severity": "High", "reason": "API dependency is blocked."}],
        }


class AzureDevOpsCenterTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "workItems": {
                "1": {"workItemId": "1", "workItemType": "User Story", "title": "Device Health", "state": "Active", "storyPoints": 5, "url": "https://example.test/workitems/1"},
                "2": {"workItemId": "2", "workItemType": "Task", "title": "Blocked API", "state": "Blocked", "tags": ["Blocked"]},
            },
            "pullRequests": {"21": {"pullRequestId": "21", "title": "Device health API", "status": "active", "sourceBranch": "refs/heads/feature/device-health", "targetBranch": "refs/heads/main", "url": "https://example.test/pr/21"}},
            "builds": {"31": {"buildId": "31", "buildNumber": "20260714.1", "definitionName": "GridHub CI", "status": "completed", "result": "failed", "finishTime": "2026-07-14T09:00:00Z"}},
        }
        self.connections = [{"connectionId": "ado-1", "projectId": "project-1", "projectName": "GridHub", "status": "Connected"}]
        self.recommendations = [{"recommendationId": "rec-1", "projectId": "project-1", "workItemId": "1", "recommendationType": "AcceptanceCriteria", "proposedValue": "Add permission validation", "status": "NeedsReview", "confidence": 88}]
        self.reports = {"report-1": {"pullRequestId": "21", "status": "NeedsReview", "acceptanceCoverage": {"score": 80}, "missingTests": ["Permission test"], "risk": {"level": "High"}}}
        self.packs = {"actionPacks": [{"packId": "pack-1", "projectId": "project-1", "trigger": "work item changed", "approvalStatus": "PendingApproval"}]}

    def service(self, *, connected=True, sprint=True, projects=None):
        return AzureDevOpsCenterService(
            sync_service=Sync(self.project_map() if projects is None else projects),
            connection_provider=lambda: self.connections if connected else [],
            sprint_service=Sprint(sprint),
            recommendation_provider=lambda: self.recommendations,
            pr_report_provider=lambda: self.reports,
            action_pack_provider=lambda: self.packs,
        )

    def project_map(self):
        return {"project-1": self.project}

    def test_dashboard_combines_ado_and_hei_intelligence(self):
        result = self.service().dashboard("project-1")
        self.assertTrue(result["connected"])
        self.assertEqual(2, result["summary"]["workItems"])
        self.assertEqual(1, result["summary"]["blockedWork"])
        self.assertEqual(1, result["summary"]["openPullRequests"])
        self.assertEqual(1, result["summary"]["pendingRecommendations"])
        self.assertEqual(1, result["summary"]["failedBuilds"])
        self.assertEqual(1, result["summary"]["pendingActions"])
        self.assertEqual([], result["releases"])
        self.assertEqual(24, result["velocity"]["currentCompletedStoryPoints"])

    def test_large_project_is_paginated_and_bounded(self):
        project = {"workItems": {str(index): {"workItemId": str(index), "title": f"Item {index}", "state": "Active"} for index in range(600)}}
        result = self.service(projects={"project-1": project}).work_items("project-1", offset=100, limit=100)
        self.assertEqual(600, result["pagination"]["total"])
        self.assertEqual(100, result["pagination"]["returned"])
        self.assertTrue(result["pagination"]["hasMore"])

    def test_no_current_sprint_is_a_professional_empty_state(self):
        result = self.service(sprint=False).sprint("project-1")
        self.assertEqual("NoSprint", result["status"])
        self.assertEqual([], result["burndownSeries"])
        self.assertIn("No current sprint", result["message"])

    def test_disconnected_ado_is_safe_and_explicit(self):
        result = self.service(connected=False, projects={}).dashboard("project-1")
        self.assertFalse(result["connected"])
        self.assertEqual("Disconnected", result["sprint"]["status"])
        self.assertIn("ado_disconnected", {item["code"] for item in result["warnings"]})
        self.assertEqual(0, result["summary"]["workItems"])

    def test_routes_match_milestone_contract(self):
        app = FastAPI()
        app.include_router(build_ado_center_router(self.service()))
        paths = ["/ado/dashboard", "/ado/sprint", "/ado/work-items", "/ado/prs"]
        client = TestClient(app)
        for path in paths:
            with self.subTest(path=path):
                response = client.get(path, params={"projectId": "project-1"})
                self.assertEqual(200, response.status_code)

    def test_center_source_exposes_operations_without_ado_writes(self):
        source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "azure-devops-extension/src/azureDevOpsCenter.tsx").read_text()
        for label in ("Open Work Item", "Open PR", "Review Recommendation", "Approve Action", "Refresh"):
            self.assertIn(label, source)
        self.assertNotIn("method: 'POST'", source)


if __name__ == "__main__":
    unittest.main()
