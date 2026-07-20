from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.planning_center import PlanningCenterService, TaskGenerationService, build_task_generation_router


def artifact(item_id: str, kind: str, title: str, parent: str = "", state: str = "draft", **payload):
    return {
        "artifact_id": item_id, "artifact_type": kind, "state": state, "title": title,
        "payload": {"parentId": parent, **payload}, "source_item": {"id": parent, "type": "Story", "title": "Parent"},
        "version": 1, "created_on": "2026-07-20T08:00:00Z",
    }


class TaskGenerationSprint15Tests(unittest.TestCase):
    def setUp(self):
        self.artifacts = [
            artifact("story-1", "Story", "View Device Health", "feature-1", state="locked"),
            artifact(
                "task-1", "Task", "Add device health API", "story-1", description="Return current health.",
                category="API", estimate={"engineeringHours": 8}, owner="Engineer A", priority="High",
                taskStatus="To Do", dependencies=["Telemetry API"], source="ai",
            ),
            artifact("task-2", "Task", "Validate device health", "story-1", category="Testing"),
        ]
        self.generated = []

        def create(request):
            item_id = f"task-{len(self.artifacts) + 1}"
            item = artifact(item_id, request["artifact_type"], request["title"], request["payload"].get("parentId", ""), state=request.get("state", "draft"), **{key: value for key, value in request["payload"].items() if key != "parentId"})
            item["source_item"] = request.get("source_item") or {}
            self.artifacts.append(item)
            return item

        def update(item_id, changes, actor):
            item = next(value for value in self.artifacts if value["artifact_id"] == item_id)
            if item["state"] not in {"draft", "review"}:
                raise ValueError("Only Draft or Review planning artifacts can be edited.")
            if changes.get("expectedVersion") is not None and int(changes["expectedVersion"]) != item["version"]:
                raise ValueError("Planning artifact version changed.")
            item["title"] = changes.get("title") or item["title"]
            item["payload"] = {**item["payload"], **changes.get("details", {})}
            if "description" in changes:
                item["payload"]["description"] = changes["description"]
            item["version"] += 1
            item["changed_by"] = actor
            return item

        def archive(item_id):
            item = next(value for value in self.artifacts if value["artifact_id"] == item_id)
            item["state"] = "archived"
            return item

        def regenerate(item_id, actor):
            item = next(value for value in self.artifacts if value["artifact_id"] == item_id)
            return update(item_id, {
                "expectedVersion": item["version"], "title": f"Regenerated {item['title']}",
                "description": "Regenerated through Planning Intelligence.",
            }, actor)

        self.planning = PlanningCenterService(
            artifact_provider=lambda: {"artifacts": self.artifacts}, artifact_approver=lambda _id, _actor: {},
            artifact_rejecter=archive, artifact_updater=update, artifact_creator=create, artifact_regenerator=regenerate,
            recommendation_provider=lambda: [], estimate_provider=lambda _project: [],
        )

        def generate(story_id, actor):
            self.generated.append((story_id, actor))
            create({
                "artifact_type": "Task", "title": "Implement device health view", "state": "draft",
                "payload": {"parentId": story_id, "description": "Render current device health.", "work_area": "Frontend Work", "source": "ai"},
            })
            return {"generatedTaskCount": 1}

        self.service = TaskGenerationService(
            planning_service=self.planning, artifact_provider=lambda: {"artifacts": self.artifacts}, ai_task_generator=generate,
        )

    def test_manual_task_captures_complete_implementation_shape_under_approved_story(self):
        result = self.service.create_for_story("story-1", {
            "mode": "manual", "title": "Add health status filter", "description": "Filter devices by health state.",
            "category": "Frontend", "estimate": {"engineeringHours": 12, "confidence": 85},
            "owner": "Engineer B", "priority": "High", "taskStatus": "In Progress",
            "dependencies": ["Device health query"],
        }, "Planner")
        task = result["tasks"][0]
        self.assertEqual("Frontend", task["category"])
        self.assertEqual(12, task["estimate"]["engineeringHours"])
        self.assertEqual(1.5, task["estimate"]["engineeringDays"])
        self.assertEqual("Engineer B", task["owner"])
        self.assertEqual("High", task["priority"])
        self.assertEqual("In Progress", task["taskStatus"])
        self.assertEqual(["Device health query"], task["dependencies"])
        self.assertEqual("manual", task["source"])

    def test_ai_generation_uses_same_task_projection(self):
        result = self.service.create_for_story("story-1", {"mode": "ai"}, "Planner")
        self.assertEqual([("story-1", "Planner")], self.generated)
        created = next(task for task in result["tasks"] if task["title"] == "Implement device health view")
        self.assertEqual("Frontend", created["category"])
        self.assertEqual("Unassigned", created["owner"])
        self.assertEqual("To Do", created["taskStatus"])

    def test_edit_regenerate_split_merge_and_delete_use_artifact_lifecycle(self):
        edited = self.service.update("task-1", {
            "title": "Add current device health API", "description": "Return health and communication state.",
            "category": "API", "estimate": {"engineeringHours": 16}, "owner": "Engineer C",
            "priority": "Critical", "taskStatus": "In Progress", "dependencies": ["Telemetry API", "Device API"],
            "expectedVersion": 1,
        }, "Planner")["task"]
        self.assertEqual("Engineer C", edited["owner"])
        self.assertEqual(2, edited["estimate"]["engineeringDays"])

        regenerated = self.service.update("task-1", {"action": "regenerate"}, "Planner")["task"]
        self.assertTrue(regenerated["title"].startswith("Regenerated"))

        split = self.service.update("task-1", {"action": "split", "titles": ["Add health query", "Map health response"]}, "Planner")
        self.assertEqual(2, split["count"])
        self.assertEqual("archived", next(item for item in self.artifacts if item["artifact_id"] == "task-1")["state"])

        task_ids = [task["id"] for task in split["tasks"]]
        merged = self.service.update(task_ids[0], {"action": "merge", "taskIds": task_ids, "title": "Deliver health API"}, "Planner")
        self.assertEqual("Deliver health API", merged["task"]["title"])
        self.service.delete(merged["task"]["id"], "Planner")
        self.assertEqual("archived", next(item for item in self.artifacts if item["artifact_id"] == merged["task"]["id"])["state"])

    def test_approved_task_cannot_be_changed_or_deleted(self):
        next(item for item in self.artifacts if item["artifact_id"] == "task-1")["state"] = "locked"
        with self.assertRaisesRegex(ValueError, "Draft or Review"):
            self.service.update("task-1", {"title": "Changed"})
        with self.assertRaisesRegex(ValueError, "Draft or Review"):
            self.service.delete("task-1")

    def test_task_routes_and_story_drawer_actions_are_available(self):
        app = FastAPI()
        app.include_router(build_task_generation_router(self.service))
        client = TestClient(app)
        created = client.post("/story/story-1/tasks?actor=Planner", json={"mode": "manual", "title": "Document health API", "category": "Documentation"})
        self.assertEqual(200, created.status_code)
        task_id = created.json()["tasks"][0]["id"]
        self.assertEqual(200, client.put(f"/task/{task_id}?actor=Planner", json={"priority": "Low", "taskStatus": "Done"}).status_code)
        self.assertEqual(200, client.delete(f"/task/{task_id}?actor=Planner").status_code)

        drawer = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "storyDetailDrawer.tsx").read_text()
        for label in ("Implementation Tasks", "Add Manual Task", "Generate AI Tasks", "Regenerate", "Split", "Merge Selected", "Delete"):
            self.assertIn(label, drawer)
        for category in ("Frontend", "Backend", "Database", "API", "Testing", "Documentation", "Deployment", "Infrastructure"):
            self.assertIn(category, drawer)


if __name__ == "__main__":
    unittest.main()
