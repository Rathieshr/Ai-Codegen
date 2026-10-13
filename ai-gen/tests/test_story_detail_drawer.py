from __future__ import annotations

import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.planning_center import PlanningCenterService, StoryDetailService, build_story_detail_router
from backend.project_intelligence import ProjectIntelligenceService


def artifact(item_id: str, kind: str, title: str, parent: str = "", state: str = "draft", **payload):
    return {
        "artifact_id": item_id,
        "artifact_type": kind,
        "state": state,
        "title": title,
        "payload": {"parentId": parent, **payload},
        "source_item": {"id": parent, "type": "Feature", "title": "Parent"},
        "version": 1,
        "created_on": "2026-07-20T08:00:00Z",
    }


class StoryDetailDrawerTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = [
            artifact("feature-1", "Feature", "Device Health", acceptanceCriteria=["Health is visible"]),
            artifact(
                "story-1", "Story", "View Device Health", "feature-1",
                description="Review current device condition.",
                acceptanceCriteria=["Operator can view device status."],
                businessRules=["Restricted devices require permission."],
                dependencies=["Telemetry API"], storyPoints=5,
                risks=["Stale telemetry"], repositoryModules=["Device Health"],
                engineeringNotes=["Reuse the existing status model."], confidence=0.88,
            ),
            artifact("story-2", "Story", "Filter Device Health", "feature-1", confidence=0.81),
            artifact("task-1", "Task", "Add health query", "story-1", description="Query current device status.", confidence=0.9),
            artifact(
                "tests-1", "Test Suite", "Device Health Tests", "story-1",
                test_suite={"test_cases": [{"id": "test-1", "title": "View healthy device", "description": "Verify healthy state.", "category": "Functional"}]},
            ),
        ]
        self.regenerated_tasks = []
        self.generated_tests = []
        self.estimates = []

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
            item["updated_on"] = "2026-07-20T09:00:00Z"
            item["changed_by"] = actor
            return item

        def reject(item_id):
            item = next(value for value in self.artifacts if value["artifact_id"] == item_id)
            item["state"] = "archived"
            return item

        def regenerate(item_id, actor):
            return update(item_id, {"expectedVersion": 1, "title": "Regenerated Device Health Story", "status": "Review"}, actor)

        self.planning = PlanningCenterService(
            artifact_provider=lambda: {"artifacts": self.artifacts},
            artifact_approver=lambda item_id, actor: {}, artifact_rejecter=reject,
            artifact_updater=update, artifact_regenerator=regenerate,
            recommendation_provider=lambda: [], estimate_provider=lambda _project_id: self.estimates,
        )
        self.service = StoryDetailService(
            planning_service=self.planning,
            artifact_provider=lambda: {"artifacts": self.artifacts},
            task_regenerator=lambda story_id, actor: self.regenerated_tasks.append((story_id, actor)) or {"generatedTaskCount": 2},
            test_generator=lambda story_id, actor: self.generated_tests.append((story_id, actor)) or {"generatedTestCount": 3},
        )

    def test_story_projection_contains_editable_planning_and_engineering_context(self):
        self.estimates.append({
            "artifactId": "story-1", "version": 2,
            "effectiveEstimate": {"engineeringDays": 4, "engineeringHours": 32, "storyPoints": 5, "confidence": 91},
        })
        result = self.service.get("story-1")
        self.assertEqual("hei-story-detail-v1", result["schemaVersion"])
        self.assertEqual(["Operator can view device status."], result["acceptanceCriteria"])
        self.assertEqual(["Restricted devices require permission."], result["businessRules"])
        self.assertEqual(["Telemetry API"], result["dependencies"])
        self.assertEqual(5, result["storyPoints"])
        self.assertEqual(4, result["estimate"]["engineeringDays"])
        self.assertEqual(["Device Health"], result["repositoryModules"])
        self.assertEqual(["task-1"], [item["id"] for item in result["generatedTasks"]])
        self.assertEqual(["test-1"], [item["id"] for item in result["generatedTests"]])
        self.assertEqual(["story-2"], [item["id"] for item in result["relatedStories"]])

    def test_story_and_generated_children_are_saved_together(self):
        result = self.service.update("story-1", {
            "expectedVersion": 1,
            "title": "Review Device Condition",
            "description": "Review live device condition and communication state.",
            "acceptanceCriteria": ["Operator can view health and communication status."],
            "businessRules": ["Access follows the device permission matrix."],
            "dependencies": ["Telemetry API", "Device API"],
            "estimate": {"engineeringDays": 3, "engineeringHours": 24, "storyPoints": 8, "confidence": 88},
            "storyPoints": 8,
            "risks": ["Telemetry may be delayed."],
            "repositoryModules": ["Device Health", "Telemetry"],
            "relatedStoryIds": ["story-2"],
            "engineeringNotes": ["Keep health state mapping centralized."],
            "generatedTasks": [{"id": "task-1", "title": "Implement device health query", "description": "Read current health and communication status.", "version": 1}],
            "generatedTests": [{"id": "test-1", "title": "View current device health", "description": "Verify current state.", "category": "Integration", "artifactId": "tests-1", "artifactVersion": 1}],
        }, "Planner")
        self.assertEqual("Review Device Condition", result["title"])
        self.assertEqual(8, result["storyPoints"])
        self.assertEqual(3, result["estimate"]["engineeringDays"])
        self.assertTrue(result["relatedStories"][0]["selected"])
        self.assertEqual("Implement device health query", result["generatedTasks"][0]["title"])
        self.assertEqual("Integration", result["generatedTests"][0]["category"])

    def test_regeneration_test_generation_and_delete_use_canonical_services(self):
        regenerated = self.service.regenerate("story-1", "Planner")
        self.assertEqual("Regenerated Device Health Story", regenerated["title"])
        self.service.regenerate_tasks("story-1", "Planner")
        self.service.generate_tests("story-1", "Planner")
        self.assertEqual([("story-1", "Planner")], self.regenerated_tasks)
        self.assertEqual([("story-1", "Planner")], self.generated_tests)
        deleted = self.service.delete("story-1", "Planner")
        self.assertEqual(3, deleted["count"])
        self.assertEqual("archived", next(item for item in self.artifacts if item["artifact_id"] == "tests-1")["state"])

    def test_approved_child_blocks_entire_save_before_story_changes(self):
        next(item for item in self.artifacts if item["artifact_id"] == "task-1")["state"] = "locked"
        with self.assertRaisesRegex(ValueError, "approved"):
            self.service.update("story-1", {
                "expectedVersion": 1, "title": "Should Not Save",
                "generatedTasks": [{"id": "task-1", "title": "Changed", "version": 1}],
            })
        self.assertEqual("View Device Health", next(item for item in self.artifacts if item["artifact_id"] == "story-1")["title"])

    def test_story_routes_and_drawer_integration_are_available(self):
        app = FastAPI()
        app.include_router(build_story_detail_router(self.service))
        client = TestClient(app)
        self.assertEqual(200, client.get("/story/story-1").status_code)
        self.assertEqual(200, client.put("/story/story-1?actor=Planner", json={"expectedVersion": 1, "title": "Updated Story"}).status_code)
        self.assertEqual(200, client.post("/story/story-1/regenerate-tasks?actor=Planner", json={}).status_code)
        self.assertEqual(200, client.post("/story/story-1/generate-tests?actor=Planner", json={}).status_code)
        hierarchy = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "planningHierarchy.tsx").read_text()
        drawer = (Path(__file__).parents[1] / "azure-devops-extension" / "src" / "storyDetailDrawer.tsx").read_text()
        self.assertIn("<StoryDetailDrawer", hierarchy)
        self.assertIn("item.type === 'Story'", hierarchy)
        for action in ("Save", "Regenerate Story", "Regenerate Tasks", "Generate Tests", "Delete"):
            self.assertIn(action, drawer)

    def test_production_story_callbacks_persist_tasks_and_tests(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "AI_GEN_DATA_DIR": temp_dir, "AI_GEN_REFINER_ENABLED": "0",
        }, clear=False):
            service = ProjectIntelligenceService()
            service.save_profile({
                "project_description": "Device health operations",
                "applications": ["Operations Dashboard"],
                "modules": ["Device Health", "Telemetry"],
                "flows": ["Device Health Review Flow"],
            })
            feature = service.save_artifact({
                "artifact_type": "Feature", "title": "Device Health Overview", "state": "draft",
                "source_item": {"id": "epic-1", "type": "Epic", "title": "Device Health"},
                "payload": {"description": "Provide device health visibility."},
            })
            story = service.save_artifact({
                "artifact_type": "Story", "title": "View Device Health", "state": "draft",
                "source_item": {"id": feature["artifact_id"], "type": "Feature", "title": feature["title"]},
                "payload": {
                    "parentId": feature["artifact_id"], "description": "Review device health and communication state.",
                    "acceptanceCriteria": ["Operator can view current device health and communication status."],
                    "repositoryModules": ["Device Health", "Telemetry"],
                },
            })
            manual = service.save_artifact({
                "artifact_type": "Task", "title": "Document device health states", "state": "draft",
                "source_item": {"id": story["artifact_id"], "type": "Story", "title": story["title"]},
                "payload": {"parentId": story["artifact_id"], "description": "Document states.", "source": "manual"},
            })
            tasks = service.regenerate_story_tasks(story["artifact_id"], "Planner")
            tests = service.generate_story_tests(story["artifact_id"], "Planner")
            persisted = service.list_artifacts()["artifacts"]

        self.assertGreater(tasks["generatedTaskCount"], 0)
        self.assertEqual(1, tasks["preservedManualTaskCount"])
        self.assertGreater(tests["generatedTestCount"], 0)
        self.assertTrue(any(item["artifact_type"] == "Task" for item in persisted))
        self.assertNotEqual("archived", next(item for item in persisted if item["artifact_id"] == manual["artifact_id"])["state"])
        self.assertTrue(any(item["artifact_type"] == "Test Suite" for item in persisted))


if __name__ == "__main__":
    unittest.main()
