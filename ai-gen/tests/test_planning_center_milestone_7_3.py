from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.planning_center import PlanningCenterService, build_planning_center_router


def artifact(index: int, kind: str = "Story", parent: str = "", state: str = "draft", **payload):
    return {
        "artifact_id": f"artifact-{index}", "artifact_type": kind, "state": state,
        "title": payload.pop("title", f"{kind} {index}"), "payload": {"parentId": parent, **payload},
        "source_item": {"id": parent or f"source-{index}", "type": "Feature", "title": "Parent"},
        "version": 1, "created_on": f"2026-07-14T00:{index % 60:02d}:00Z",
    }


class PlanningCenterTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = []
        self.recommendations = []
        self.approved = []
        self.rejected = []
        self.service = PlanningCenterService(
            artifact_provider=lambda: {"artifacts": self.artifacts, "count": len(self.artifacts)},
            artifact_approver=lambda item_id, actor: self.approved.append((item_id, actor)) or {"artifact_id": item_id, "state": "locked"},
            artifact_rejecter=lambda item_id: self.rejected.append(item_id) or {"artifact_id": item_id, "state": "archived"},
            recommendation_provider=lambda: self.recommendations,
            recommendation_approver=lambda item_id, actor: {"recommendationId": item_id, "status": "Approved", "actor": actor},
            recommendation_rejecter=lambda item_id, actor: {"recommendationId": item_id, "status": "Rejected", "actor": actor},
        )

    def test_large_backlog_is_bounded_and_paginated(self):
        self.artifacts = [artifact(index) for index in range(600)]
        first = self.service.list(limit=200)
        second = self.service.list(offset=200, limit=200)
        self.assertEqual(600, first["pagination"]["total"])
        self.assertEqual(200, len(first["items"]))
        self.assertTrue(first["pagination"]["hasMore"])
        self.assertEqual(200, second["pagination"]["offset"])
        self.assertEqual("artifact-599", self.service.get("artifact-599")["id"])

    def test_deep_hierarchy_uses_iterative_depth_calculation(self):
        self.artifacts = [artifact(0, "Epic")]
        parent = "artifact-0"
        for index in range(1, 80):
            self.artifacts.append(artifact(index, "Feature" if index == 1 else "Story", parent=parent))
            parent = f"artifact-{index}"
        result = self.service.list(limit=100)
        deepest = next(item for item in result["items"] if item["id"] == "artifact-79")
        self.assertEqual(79, deepest["depth"])
        self.assertEqual(1, next(item for item in result["items"] if item["id"] == "artifact-0")["childCount"])

    def test_approval_and_rejection_use_persisted_artifact_actions(self):
        self.artifacts = [artifact(1)]
        self.assertEqual("locked", self.service.approve("artifact-1", "Planner")["state"])
        self.assertEqual("archived", self.service.reject("artifact-1", "Planner")["state"])
        self.assertEqual([("artifact-1", "Planner")], self.approved)
        self.assertEqual(["artifact-1"], self.rejected)

    def test_filtering_by_type_status_and_readiness(self):
        self.artifacts = [
            artifact(1, "Epic", state="locked", confidence=95),
            artifact(2, "Story", risks=["Security review required"], confidence=60),
            artifact(3, "Task", confidence=80),
        ]
        approved = self.service.list(item_type="Epic", status="Approved")
        needs_review = self.service.list(readiness="Needs Review")
        self.assertEqual(["artifact-1"], [item["id"] for item in approved["items"]])
        self.assertEqual(["artifact-2"], [item["id"] for item in needs_review["items"]])

    def test_search_covers_title_dependency_and_risk(self):
        self.artifacts = [
            artifact(1, title="Device Health Overview", dependencies=["Telemetry API"]),
            artifact(2, title="User Administration", risks=["Permission regression"]),
        ]
        by_title = self.service.list(search="device health")
        by_dependency = self.service.list(search="telemetry")
        by_risk = self.service.list(search="permission regression")
        self.assertEqual(["artifact-1"], [item["id"] for item in by_title["items"]])
        self.assertEqual(["artifact-1"], [item["id"] for item in by_dependency["items"]])
        self.assertEqual(["artifact-2"], [item["id"] for item in by_risk["items"]])

    def test_required_api_contracts(self):
        self.artifacts = [artifact(1, "Story", state="locked")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        client = TestClient(app)
        self.assertEqual(200, client.get("/planning").status_code)
        self.assertEqual(200, client.get("/planning/artifact-1").status_code)
        self.assertEqual(200, client.get("/planning/recommendations").status_code)
        self.assertEqual(200, client.post("/planning/artifact-1/approve", json={"actor": "Planner"}).status_code)

    def test_planning_review_shows_estimation_report_before_approval(self):
        source = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningCenter.tsx").read_text()
        self.assertIn("Engineering Estimation Report", source)
        self.assertIn("/planning/estimate", source)
        self.assertIn("Top Estimation Drivers", source)
        self.assertIn("Repository Reuse", source)
        self.assertIn("Edit Estimate", source)
        self.assertIn("!selectedEstimate", source)
        self.assertLess(source.index("<EstimationReport"), source.index("className=\"hei-planning-actions\""))


if __name__ == "__main__":
    unittest.main()
