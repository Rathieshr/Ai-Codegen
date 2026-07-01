import tempfile
import unittest
from pathlib import Path

from backend.lifecycle import EngineeringLifecycleManager


class EngineeringLifecycleManagerTests(unittest.TestCase):
    def test_story_approved_allows_generate_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EngineeringLifecycleManager(Path(tmp) / "lifecycle.json")
            lifecycle = manager.get_lifecycle(
                {"id": 42, "type": "Story", "state": "Approved"},
                {"has_tasks": False},
            )

            self.assertEqual(lifecycle["currentState"], "Approved")
            self.assertEqual(lifecycle["currentStage"], "Planning")
            self.assertEqual(lifecycle["nextAction"], "Generate Tasks")
            self.assertIn("Generate Tasks", lifecycle["allowedActions"])
            self.assertEqual(lifecycle["currentOwner"], "Product Owner")

    def test_task_approved_allows_build_execution_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EngineeringLifecycleManager(Path(tmp) / "lifecycle.json")
            lifecycle = manager.get_lifecycle(
                {"id": 91, "type": "Task", "state": "Approved"},
                {"has_execution_package": False},
            )

            self.assertEqual(lifecycle["nextAction"], "Build Execution Package")
            self.assertIn("Build Execution Package", lifecycle["allowedActions"])

    def test_qa_blocked_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EngineeringLifecycleManager(Path(tmp) / "lifecycle.json")
            lifecycle = manager.get_lifecycle(
                {"id": "qa_1", "type": "QA Report", "state": "Release Ready"},
                {"qa_status": "Blocked"},
            )

            blocked_actions = {item["action"] for item in lifecycle["blockedActions"]}
            self.assertIn("Release", blocked_actions)

    def test_advance_persists_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EngineeringLifecycleManager(Path(tmp) / "lifecycle.json")
            advanced = manager.advance(
                {"id": "story_1", "type": "Story", "state": "Draft"},
                "Analyzed",
                "tester",
            )
            history = manager.history_for("story_1")

            self.assertEqual(advanced["currentState"], "Analyzed")
            self.assertEqual(len(history["history"]), 1)
            self.assertEqual(history["history"][0]["eventType"], "advance")

    def test_rollback_moves_to_previous_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EngineeringLifecycleManager(Path(tmp) / "lifecycle.json")
            manager.advance({"id": "task_1", "type": "Task", "state": "Approved"}, "Execution Ready", "tester")
            rolled_back = manager.rollback({"id": "task_1", "type": "Task"}, "tester")

            self.assertEqual(rolled_back["currentState"], "Approved")
            self.assertEqual(rolled_back["transition"]["reason"], "Rolled back to previous lifecycle state.")


if __name__ == "__main__":
    unittest.main()
