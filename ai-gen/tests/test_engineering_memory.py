import tempfile
import unittest
from pathlib import Path

from backend.engineering_memory import EngineeringMemoryEngine


def approved_memory(**overrides):
    payload = {
        "projectId": "LineDefender",
        "category": "Planning Memory",
        "title": "Review Critical Fault Details",
        "summary": "Operations users review critical fault details from the fault event workflow.",
        "content": "Approved story pattern for critical fault review with telemetry and device health context.",
        "artifactType": "Story",
        "artifactId": "34",
        "knowledgeReferences": ["Fault Monitoring", "Telemetry", "Fault Event Review Flow"],
        "tags": ["fault", "operations", "story"],
        "confidence": 0.92,
        "source": {"status": "Approved"},
    }
    payload.update(overrides)
    return payload


class EngineeringMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = EngineeringMemoryEngine(Path(self.tmp.name) / "engineering_memory.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_store_approved_story(self):
        result = self.engine.store_memory(approved_memory(), "Rathiesh")

        self.assertTrue(result["stored"])
        memory = result["memory"]
        self.assertEqual(memory["artifactType"], "Story")
        self.assertEqual(memory["approvalStatus"], "Validated")
        self.assertIn("Fault Monitoring", memory["knowledgeReferences"])

    def test_store_approved_execution_package(self):
        result = self.engine.store_memory(
            approved_memory(
                category="Execution Memory",
                title="Fault Details Execution Package",
                artifactType="Execution Package",
                artifactId="pkg-1",
                content="Use execution package with repository-ranked context for fault details.",
                tags=["execution", "fault"],
                source={"validationStatus": "Passed"},
            )
        )

        self.assertTrue(result["stored"])
        self.assertEqual(result["memory"]["category"], "Execution Memory")

    def test_store_successful_qa_pattern(self):
        result = self.engine.store_memory(
            approved_memory(
                category="QA Memory",
                title="Permission Tests For Fault Review",
                artifactType="Test Suite",
                artifactId="qa-7",
                summary="Permission and negative tests for restricted fault event access.",
                tags=["qa", "permission", "negative"],
                source={"status": "Ready For Release"},
            )
        )

        self.assertTrue(result["stored"])
        self.assertEqual(result["memory"]["category"], "QA Memory")

    def test_retrieve_similar_story(self):
        self.engine.store_memory(approved_memory())
        memory_id = self.engine.list_memory()["memories"][0]["id"]
        self.engine.approve_memory(memory_id)
        self.engine.index_memory(memory_id)

        result = self.engine.find_reusable_stories({"query": "fault telemetry story", "includeDrafts": False})

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["artifactType"], "Story")
        self.assertIn("keyword", result["results"][0]["matchReasons"])

    def test_retrieve_architecture_decisions(self):
        self.engine.store_memory(
            approved_memory(
                category="Architecture Memory",
                title="Fault Monitoring Uses Telemetry Gateway",
                artifactType="Decision",
                artifactId="adr-1",
                summary="Decision: route fault monitoring reads through the telemetry gateway.",
                tags=["architecture", "decision", "Telemetry"],
                source={"status": "Approved"},
            )
        )
        memory_id = self.engine.list_memory()["memories"][0]["id"]
        self.engine.approve_memory(memory_id)

        result = self.engine.find_architecture({"architecture": True})

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["category"], "Architecture Memory")

    def test_version_memory_resets_approved_memory_to_draft(self):
        stored = self.engine.store_memory(approved_memory())["memory"]
        self.engine.approve_memory(stored["id"])

        updated = self.engine.update_memory(stored["id"], {"summary": "Updated approved story pattern."}, "Admin")["memory"]

        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["approvalStatus"], "Draft")
        self.assertEqual(updated["history"][-1]["event"], "version_created")

    def test_reject_duplicate_memory(self):
        first = self.engine.store_memory(approved_memory())
        second = self.engine.store_memory(approved_memory())

        self.assertTrue(first["stored"])
        self.assertFalse(second["stored"])
        self.assertTrue(second["duplicate"])

    def test_archive_obsolete_memory(self):
        stored = self.engine.store_memory(approved_memory())["memory"]

        archived = self.engine.archive_memory(stored["id"], "Admin")["memory"]

        self.assertEqual(archived["approvalStatus"], "Archived")

    def test_reject_failed_artifact(self):
        result = self.engine.store_memory(approved_memory(source={"status": "Failed"}))

        self.assertFalse(result["stored"])
        self.assertIn("cannot become Engineering Memory", result["reason"])


if __name__ == "__main__":
    unittest.main()
