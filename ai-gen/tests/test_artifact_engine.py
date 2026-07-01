from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.artifacts import ArtifactDefinition, ArtifactEngine, ArtifactRepository, ArtifactStatus


class ArtifactEngineTests(unittest.TestCase):
    def test_feature_and_story_share_lifecycle(self) -> None:
        engine = ArtifactEngine()

        for artifact_type in ["Feature", "Story"]:
            artifact = engine.create(
                artifact_type,
                {
                    "title": f"{artifact_type} Fault Event Review",
                    "description": "Review critical fault event details.",
                    "businessValue": "Faster outage triage.",
                    "acceptanceThemes": ["Fault event details are reviewable."],
                    "confidence": 0.9,
                },
            )
            artifact = engine.analyze(artifact)
            artifact = engine.generate(artifact)
            artifact = engine.validate(artifact)
            artifact = engine.build_dna(artifact)
            artifact = engine.version(artifact)
            artifact = engine.approve(artifact)

            self.assertEqual(artifact["type"], artifact_type)
            self.assertEqual(artifact["status"], ArtifactStatus.APPROVED)
            self.assertEqual(artifact["version"], 1)
            self.assertTrue(artifact["dna"]["dnaId"])
            self.assertGreaterEqual(len(artifact["lifecycleHistory"]), 6)

    def test_artifact_definition_plugs_in_strategies_only(self) -> None:
        definition = ArtifactDefinition(
            artifact_type="Task",
            analysis_strategy=lambda source, context: {"responsibilities": ["Backend API"]},
            generation_strategy=lambda source, context: {"description": "Add a fault-event detail endpoint."},
            validation_strategy=lambda artifact, context: {"validationStatus": "Approved", "issues": [], "score": 100},
            dna_builder=lambda artifact, context: {"dnaId": "dna_task_backend_api", "capability": "Fault Event Details"},
        )
        engine = ArtifactEngine()
        engine.factory.definitions["Task"] = definition

        artifact = engine.create("Task", {"title": "Add detail API", "confidence": 0.95})
        artifact = engine.analyze(artifact)
        artifact = engine.generate(artifact)
        artifact = engine.validate(artifact)
        artifact = engine.build_dna(artifact)

        self.assertEqual(artifact["responsibilities"], ["Backend API"])
        self.assertEqual(artifact["description"], "Add a fault-event detail endpoint.")
        self.assertEqual(artifact["validation"]["validationStatus"], "Approved")
        self.assertEqual(artifact["dna"]["capability"], "Fault Event Details")

    def test_version_manager_reuses_version_when_fingerprint_unchanged(self) -> None:
        engine = ArtifactEngine()
        artifact = engine.create("Story", {"title": "Open fault event details", "description": "Review event context.", "confidence": 0.9})
        first = engine.version(artifact)
        second = engine.version(first, previous=first)
        changed = engine.version({**second, "description": "Review event and device context."}, previous=second)

        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 1)
        self.assertFalse(second["changed"])
        self.assertEqual(changed["version"], 2)
        self.assertTrue(changed["changed"])

    def test_repository_can_persist_artifacts_to_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifacts.json"
            engine = ArtifactEngine(repository=ArtifactRepository(path))
            artifact = engine.create("Epic", {"title": "Real-Time Fault Monitoring", "confidence": 0.8})

            reloaded = ArtifactRepository(path)

        self.assertEqual(reloaded.get(artifact["id"])["title"], "Real-Time Fault Monitoring")

    def test_invalid_transition_is_recorded_without_status_change(self) -> None:
        engine = ArtifactEngine()
        artifact = engine.create("Feature", {"title": "Operator Alerting", "confidence": 0.9})
        artifact = engine.publish(artifact)

        self.assertEqual(artifact["status"], ArtifactStatus.DRAFT)
        self.assertFalse(artifact["lifecycleHistory"][-1]["allowed"])
        self.assertIn("approved", artifact["lifecycleHistory"][-1]["reason"].lower())


if __name__ == "__main__":
    unittest.main()
