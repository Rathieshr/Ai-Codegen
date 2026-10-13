from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.planning_center import (
    PlanningCenterService,
    PlanningDependencyService,
    build_planning_dependency_router,
)


def artifact(index: int, kind: str, parent: str = "", state: str = "draft", **payload):
    return {
        "artifact_id": f"artifact-{index}",
        "artifact_type": kind,
        "state": state,
        "title": payload.pop("title", f"{kind} {index}"),
        "payload": {"parentId": parent, **payload},
        "source_item": {"id": parent or f"source-{index}", "type": "Epic", "title": "Parent"},
        "version": 1,
        "created_on": f"2026-07-20T00:{index:02d}:00Z",
    }


class PlanningDependencyTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = [
            artifact(1, "Epic", title="Device Health Planning"),
            artifact(2, "Feature", "artifact-1", title="Device Health API", storyPoints=3),
            artifact(3, "Story", "artifact-2", title="Show Health Overview", storyPoints=5),
            artifact(4, "Task", "artifact-3", title="Implement Health Query", storyPoints=2),
        ]

        def update_artifact(item_id, changes, actor):
            item = next(value for value in self.artifacts if value["artifact_id"] == item_id)
            if item["state"] not in {"draft", "review"}:
                raise ValueError("Only Draft or Review planning artifacts can be edited.")
            if changes.get("expectedVersion") is not None and changes["expectedVersion"] != item["version"]:
                raise ValueError("Planning artifact version changed.")
            item["payload"] = {**item["payload"], **changes.get("details", {})}
            item["version"] += 1
            item["changed_by"] = actor
            return item

        self.planning = PlanningCenterService(
            artifact_provider=lambda: {"artifacts": self.artifacts},
            artifact_approver=lambda item_id, actor: {},
            artifact_rejecter=lambda item_id: {},
            artifact_updater=update_artifact,
        )
        self.service = PlanningDependencyService(
            planning_service=self.planning,
            artifact_provider=lambda: {"artifacts": self.artifacts},
        )
        app = FastAPI()
        app.include_router(build_planning_dependency_router(self.service))
        self.client = TestClient(app)

    def put(self, source_id: str, target_id: str, dependency_type: str = "Depends On"):
        return self.client.put("/dependency?actor=Planner", json={
            "planningId": "artifact-1",
            "sourceId": source_id,
            "targetId": target_id,
            "dependencyType": dependency_type,
            "reason": "Execution order",
        })

    def test_dependency_api_projects_tree_graph_and_table(self):
        created = self.put("artifact-3", "artifact-2", "Blocked By")
        self.assertEqual(200, created.status_code)
        response = self.client.get("/planning/artifact-1/dependencies")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("hei-planning-dependencies-v1", payload["schemaVersion"])
        self.assertEqual("Blocked By", payload["dependencies"][0]["dependencyType"])
        self.assertEqual(1, len(payload["tree"]))
        self.assertEqual(1, len(payload["graph"]["edges"]))
        self.assertEqual(payload["dependencies"], payload["table"])

    def test_put_is_versioned_and_delete_removes_canonical_and_legacy_link(self):
        response = self.put("artifact-3", "artifact-2")
        dependency_id = response.json()["dependencyId"]
        story = self.artifacts[2]
        self.assertEqual(2, story["version"])
        self.assertEqual(["Device Health API"], story["payload"]["dependencies"])
        self.assertEqual(dependency_id, story["payload"]["dependencyLinks"][0]["dependencyId"])

        updated = self.client.put("/dependency", json={
            "planningId": "artifact-1", "dependencyId": dependency_id,
            "sourceId": "artifact-3", "targetId": "artifact-2", "dependencyType": "Blocked By",
        })
        self.assertEqual(200, updated.status_code)
        self.assertEqual("Blocked By", story["payload"]["dependencyLinks"][0]["dependencyType"])

        deleted = self.client.request("DELETE", "/dependency?actor=Planner", json={"dependencyId": dependency_id})
        self.assertEqual(200, deleted.status_code)
        self.assertEqual([], story["payload"]["dependencyLinks"])
        self.assertEqual([], story["payload"]["dependencies"])

    def test_circular_dependency_is_blocking_and_excluded_from_critical_path(self):
        self.put("artifact-3", "artifact-2")
        self.put("artifact-2", "artifact-3")
        result = self.service.get("artifact-1")
        self.assertEqual(["Circular", "Circular"], [item["status"] for item in result["dependencies"]])
        self.assertEqual(2, result["summary"]["circular"])
        self.assertEqual("Circular Dependency", result["warnings"][0]["type"])
        self.assertEqual([], result["criticalPath"]["dependencyIds"])

    def test_missing_legacy_and_archived_targets_have_distinct_warnings(self):
        self.artifacts[2]["payload"]["dependencies"] = ["Unknown Gateway"]
        self.artifacts.append(artifact(5, "Task", "artifact-3", state="archived", title="Retired Adapter"))
        self.artifacts[3]["payload"]["dependencyLinks"] = [{
            "dependencyId": "dep-broken", "sourceId": "artifact-4", "targetId": "artifact-5",
            "targetReference": "Retired Adapter", "dependencyType": "Depends On",
        }]
        result = self.service.get("artifact-1")
        self.assertEqual(1, result["summary"]["missing"])
        self.assertEqual(1, result["summary"]["broken"])
        self.assertEqual({"Missing Dependency", "Broken Dependency"}, {warning["type"] for warning in result["warnings"]})

    def test_critical_path_follows_prerequisite_to_dependent_order(self):
        self.put("artifact-3", "artifact-2")
        self.put("artifact-4", "artifact-3")
        result = self.service.get("artifact-1")
        self.assertEqual(["Active", "Active"], [item["status"] for item in result["dependencies"]])
        path = result["criticalPath"]
        self.assertEqual(["artifact-2", "artifact-3", "artifact-4"], path["nodeIds"])
        self.assertEqual(["Device Health API", "Show Health Overview", "Implement Health Query"], path["titles"])
        self.assertEqual(10, path["totalWeight"])

    def test_approved_source_and_source_move_are_rejected(self):
        response = self.put("artifact-3", "artifact-2")
        dependency_id = response.json()["dependencyId"]
        moved = self.client.put("/dependency", json={
            "planningId": "artifact-1", "dependencyId": dependency_id,
            "sourceId": "artifact-4", "targetId": "artifact-2", "dependencyType": "Depends On",
        })
        self.assertEqual(409, moved.status_code)
        self.artifacts[2]["state"] = "locked"
        blocked = self.client.put("/dependency", json={
            "planningId": "artifact-1", "dependencyId": dependency_id,
            "sourceId": "artifact-3", "targetId": "artifact-2", "dependencyType": "Depends On",
        })
        self.assertEqual(409, blocked.status_code)

    def test_workspace_exposes_three_views_and_dependency_mutations(self):
        root = Path(__file__).parents[1]
        center = (root / "azure-devops-extension" / "src" / "planningCenter.tsx").read_text()
        workspace = (root / "azure-devops-extension" / "src" / "planningDependencies.tsx").read_text()
        for view in ("Tree", "Graph", "Table"):
            self.assertIn(f"'{view}'", workspace)
        for warning in ("Circular Dependency", "Missing Dependency", "Broken Dependency"):
            self.assertIn(warning, Path(root / "backend" / "planning_center" / "dependency_service.py").read_text())
        self.assertIn("/planning/${encodeURIComponent(planningId)}/dependencies", center)
        self.assertIn("`${baseUrl}/dependency", center)
        self.assertIn("Critical Path", workspace)


if __name__ == "__main__":
    unittest.main()
