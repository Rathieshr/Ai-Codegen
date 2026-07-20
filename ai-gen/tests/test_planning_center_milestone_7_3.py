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
        self.estimates = []
        self.regenerated = []

        def update_artifact(item_id, changes, actor):
            item = next(value for value in self.artifacts if value["artifact_id"] == item_id)
            if item["state"] not in {"draft", "review"}:
                raise ValueError("Only Draft or Review planning artifacts can be edited.")
            if changes.get("expectedVersion") is not None and changes["expectedVersion"] != item["version"]:
                raise ValueError("Planning artifact version changed.")
            item["title"] = changes.get("title") or item["title"]
            item["payload"] = {**item["payload"], **changes.get("details", {}), "description": changes.get("description") or item["payload"].get("description", "")}
            item["state"] = str(changes.get("status") or item["state"]).lower()
            item["version"] += 1
            item["updated_on"] = "2026-07-20T12:00:00Z"
            item["changed_by"] = actor
            return item

        def create_artifact(value):
            index = len(self.artifacts) + 100
            created = {
                "artifact_id": f"artifact-{index}", "artifact_type": value["artifact_type"], "state": value.get("state", "draft"),
                "title": value["title"], "payload": value.get("payload", {}), "source_item": value.get("source_item", {}),
                "version": 1, "created_on": "2026-07-20T12:00:00Z",
            }
            self.artifacts.append(created)
            return created

        def regenerate_artifact(item_id, actor):
            self.regenerated.append((item_id, actor))
            return update_artifact(item_id, {"title": "Regenerated Story", "status": "Review"}, actor)

        def reject_artifact(item_id):
            self.rejected.append(item_id)
            item = next(value for value in self.artifacts if value["artifact_id"] == item_id)
            item["state"] = "archived"
            return item

        self.service = PlanningCenterService(
            artifact_provider=lambda: {"artifacts": self.artifacts, "count": len(self.artifacts)},
            artifact_approver=lambda item_id, actor: self.approved.append((item_id, actor)) or {"artifact_id": item_id, "state": "locked"},
            artifact_rejecter=reject_artifact,
            artifact_updater=update_artifact,
            artifact_creator=create_artifact,
            artifact_regenerator=regenerate_artifact,
            recommendation_provider=lambda: self.recommendations,
            recommendation_approver=lambda item_id, actor: {"recommendationId": item_id, "status": "Approved", "actor": actor},
            recommendation_rejecter=lambda item_id, actor: {"recommendationId": item_id, "status": "Rejected", "actor": actor},
            estimate_provider=lambda _project_id: self.estimates,
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

    def test_hierarchy_api_returns_only_selected_subtree(self):
        self.artifacts = [artifact(1, "Epic"), artifact(2, "Feature", parent="artifact-1"), artifact(3, "Story")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        response = TestClient(app).get("/planning/artifact-1/hierarchy")
        self.assertEqual(200, response.status_code)
        self.assertEqual("hei-planning-hierarchy-v1", response.json()["schemaVersion"])
        self.assertEqual(["artifact-1", "artifact-2"], [item["id"] for item in response.json()["nodes"]])

    def test_hierarchy_node_edit_move_duplicate_and_regenerate_are_versioned(self):
        self.artifacts = [
            artifact(1, "Epic"), artifact(2, "Feature", parent="artifact-1"),
            artifact(3, "Feature", parent="artifact-1"), artifact(4, "Story", parent="artifact-2"),
        ]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        client = TestClient(app)
        edited = client.put("/planning/node?actor=Manager", json={
            "nodeId": "artifact-4", "action": "edit", "expectedVersion": 1,
            "title": "Review Device Health", "storyPoints": 5, "dependencies": ["Telemetry API"],
        })
        self.assertEqual(200, edited.status_code)
        self.assertEqual(5, edited.json()["storyPoints"])
        moved = client.put("/planning/node?actor=Manager", json={
            "nodeId": "artifact-4", "action": "move", "expectedVersion": 2, "parentId": "artifact-3", "order": 0,
        })
        self.assertEqual(200, moved.status_code)
        self.assertEqual("artifact-3", moved.json()["parentId"])
        duplicate = client.put("/planning/node?actor=Manager", json={"nodeId": "artifact-4", "action": "duplicate"})
        self.assertEqual(200, duplicate.status_code)
        self.assertEqual("Review Device Health Copy", duplicate.json()["title"])
        regenerated = client.post("/planning/node/regenerate?actor=Manager", json={"nodeId": "artifact-4"})
        self.assertEqual(200, regenerated.status_code)
        self.assertEqual("Regenerated Story", regenerated.json()["title"])
        self.assertEqual([("artifact-4", "Manager")], self.regenerated)

    def test_invalid_parent_move_and_version_conflict_are_blocked(self):
        self.artifacts = [artifact(1, "Epic"), artifact(2, "Feature", parent="artifact-1"), artifact(3, "Story", parent="artifact-2")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        client = TestClient(app)
        invalid_parent = client.put("/planning/node", json={"nodeId": "artifact-3", "action": "move", "parentId": "artifact-1"})
        stale = client.put("/planning/node", json={"nodeId": "artifact-3", "action": "edit", "expectedVersion": 99, "title": "Changed"})
        self.assertEqual(409, invalid_parent.status_code)
        self.assertIn("must belong to a Feature", invalid_parent.json()["error"]["message"])
        self.assertEqual(409, stale.status_code)

    def test_delete_requires_cascade_and_archives_bottom_up(self):
        self.artifacts = [artifact(1, "Epic"), artifact(2, "Feature", parent="artifact-1"), artifact(3, "Story", parent="artifact-2")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        client = TestClient(app)
        blocked = client.request("DELETE", "/planning/node", json={"nodeId": "artifact-1"})
        deleted = client.request("DELETE", "/planning/node", json={"nodeId": "artifact-1", "cascade": True})
        self.assertEqual(409, blocked.status_code)
        self.assertEqual(200, deleted.status_code)
        self.assertEqual(["artifact-3", "artifact-2", "artifact-1"], deleted.json()["archivedNodeIds"])

    def test_split_and_merge_require_leaf_siblings(self):
        self.artifacts = [artifact(1, "Epic"), artifact(2, "Feature", parent="artifact-1"), artifact(3, "Feature", parent="artifact-1")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        client = TestClient(app)
        split = client.put("/planning/node?actor=Manager", json={"nodeId": "artifact-2", "action": "split", "titles": ["Feature A", "Feature B"]})
        self.assertEqual(200, split.status_code)
        self.assertEqual(2, split.json()["count"])

        self.artifacts = [artifact(10, "Epic"), artifact(11, "Feature", parent="artifact-10"), artifact(12, "Feature", parent="artifact-10")]
        merged = client.put("/planning/node?actor=Manager", json={"nodeId": "artifact-11", "nodeIds": ["artifact-11", "artifact-12"], "action": "merge", "title": "Unified Feature"})
        self.assertEqual(200, merged.status_code)
        self.assertEqual("Unified Feature", merged.json()["node"]["title"])

    def test_workspace_update_and_save_are_versioned_draft_operations(self):
        self.artifacts = [artifact(1, "Epic", description="Initial planning description")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        client = TestClient(app)
        updated = client.put("/planning/artifact-1?actor=Manager", json={
            "title": "Device Health Planning Pack", "description": "Reviewed scope", "status": "Review", "expectedVersion": 1,
        })
        self.assertEqual(200, updated.status_code)
        self.assertEqual("Review", updated.json()["status"])
        self.assertEqual(2, updated.json()["version"])
        saved = client.post("/planning/artifact-1/save?actor=Manager", json={"description": "Saved draft", "expectedVersion": 2})
        self.assertEqual(200, saved.status_code)
        self.assertEqual("Draft", saved.json()["status"])
        self.assertEqual(3, saved.json()["version"])

    def test_approved_workspace_is_immutable(self):
        self.artifacts = [artifact(1, "Epic", state="locked")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        response = TestClient(app).put("/planning/artifact-1", json={"title": "Changed"})
        self.assertEqual(409, response.status_code)
        self.assertEqual("planning_update_conflict", response.json()["error"]["code"])

    def test_planning_review_shows_estimation_report_before_approval(self):
        source = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningCenter.tsx").read_text()
        self.assertIn("Engineering Estimation Report", source)
        self.assertIn("/planning/estimate", source)
        self.assertIn("Top Estimation Drivers", source)
        self.assertIn("Repository Reuse", source)
        self.assertIn("Edit Estimate", source)
        self.assertIn("Boolean(selectedEstimate)", source)
        self.assertLess(source.index("<EstimationReport"), source.index("className=\"hei-planning-actions\""))

    def test_workspace_uses_single_tabbed_enterprise_shell(self):
        source = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningCenter.tsx").read_text()
        components = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningWorkspace.tsx").read_text()
        for tab in ("Overview", "Hierarchy", "Traceability", "Dependencies", "Estimate", "Review", "Approval"):
            self.assertIn(tab, components)
        for component in ("PlanningWorkspace", "PlanningTabs", "PlanningHeader", "PlanningContent", "PlanningActions", "PlanningStatusBadge", "PlanningVersion"):
            self.assertIn(f"function {component}", components)
        self.assertIn("/save?actor=", source)
        self.assertIn("Save Draft", components)

    def test_executive_overview_aggregates_pack_scope_and_estimate(self):
        self.artifacts = [
            artifact(0, "PlanningPack", title="Modernize Device Health", requirementSummary={
                "title": "Modernize Device Health", "confidence": 0.89, "qualityScore": 92,
                "repository": {"repositoryId": "repo-1", "name": "Device Operations", "branch": "main"},
                "dependencies": ["Telemetry API"], "openQuestions": ["Confirm offline threshold"],
                "acceptanceCriteria": ["Operators can filter offline devices."],
                "planningReadiness": {"status": "Ready", "score": 92, "blockers": [], "warnings": []},
            }, contextCapsule={"status": "Ready", "warnings": []}),
            artifact(1, "Feature", parent="artifact-0", title="Device Health Overview"),
            artifact(2, "Story", parent="artifact-1", title="View Offline Devices"),
            artifact(3, "Task", parent="artifact-2", title="Add Offline Filter"),
        ]
        self.estimates = [{
            "estimateId": "estimate-1", "artifactId": "artifact-0", "version": 1,
            "effectiveEstimate": {
                "engineeringDays": 12.5, "estimatedSprintCount": 1.5, "repositoryReuse": 64,
                "storyPoints": 21, "risk": "Medium", "taskEstimates": [
                    {"taskName": "Add Offline Filter", "estimatedDurationHours": 10},
                ],
                "report": {"engineeringDays": 12.5, "estimatedSprintCount": 1.5, "repositoryReuse": 64, "storyPoints": 21, "risk": "Medium"},
            },
        }]

        overview = self.service.overview("artifact-0")
        self.assertEqual("hei-planning-overview-v1", overview["schemaVersion"])
        self.assertEqual("Device Operations", overview["requirement"]["repository"])
        self.assertEqual(89, overview["requirement"]["confidence"])
        self.assertEqual({"features": 1, "stories": 1, "tasks": 1, "dependencies": 1}, overview["cards"]["planningMetrics"])
        self.assertEqual(12.5, overview["metrics"]["engineeringDays"])
        self.assertEqual(64, overview["metrics"]["repositoryReuse"])
        self.assertEqual("estimate-1", overview["engineeringEstimate"]["estimateId"])
        self.assertEqual(1, overview["charts"]["storyDistribution"][0]["value"])
        self.assertEqual(10.0, overview["charts"]["estimateBreakdown"][0]["value"])

    def test_overview_api_and_manager_actions_are_exposed(self):
        self.artifacts = [artifact(1, "PlanningPack", title="Planning Pack")]
        app = FastAPI()
        app.include_router(build_planning_center_router(self.service))
        response = TestClient(app).get("/planning/artifact-1/overview")
        self.assertEqual(200, response.status_code)
        source = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningOverview.tsx").read_text()
        for label in ("Review Hierarchy", "Review Estimate", "Review Dependencies", "Approve Planning"):
            self.assertIn(label, source)
        for chart in ("Story Distribution", "Task Distribution", "Estimate Breakdown"):
            self.assertIn(chart, source)


if __name__ == "__main__":
    unittest.main()
