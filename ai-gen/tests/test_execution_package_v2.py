import os
import tempfile
import unittest
from unittest.mock import patch

from backend.execution import build_execution_package_v2
from backend.project_intelligence import ProjectIntelligenceService


class ExecutionPackageV2Tests(unittest.TestCase):
    def test_builds_developer_ready_package_from_context_capsule(self) -> None:
        story = {
            "id": 42,
            "feature_id": 21,
            "epic_id": 7,
            "title": "Open critical fault event details",
            "description": "As an Operations User, I want to open critical fault event details.",
        }
        task = {
            "id": 91,
            "title": "Add fault event details API",
            "description": "Expose fault event severity, timestamp, and device health.",
            "work_area": "Backend Work",
        }
        capsule = {
            "capsuleId": "execution_abc",
            "capsuleType": "execution",
            "sourceWorkItemId": 91,
            "parentStoryId": 42,
            "knowledgeVersion": "kv-1",
            "repositorySnapshotVersion": "rs-1",
            "generatedAt": "2026-06-30T00:00:00+00:00",
            "selectedCapabilities": ["Critical Fault Detection"],
            "selectedModules": ["Fault Monitoring", "Telemetry"],
            "selectedFlows": ["Fault Event Review Flow"],
            "selectedApplications": ["Operations Dashboard"],
            "selectedDependencies": ["Telemetry freshness"],
            "selectedStandards": ["Repository Pattern"],
            "acceptanceCriteria": ["Fault event details show severity and device health."],
            "inScope": ["Expose approved fault event fields."],
            "outOfScope": ["Firmware rollout changes."],
            "relevantFiles": [
                {
                    "path": "src/fault/FaultEventController.cs",
                    "confidence": 0.92,
                    "reason": "Controller handles fault event details.",
                    "evidence": "FaultEventController exposes detail endpoint.",
                    "source": "repository_intelligence",
                }
            ],
            "fileRankingStatus": "Repository file ranking available",
            "rejectedContext": [{"type": "module", "name": "Firmware Management", "reason": "No firmware intent."}],
            "risks": ["Telemetry may be stale."],
            "constraints": ["Respect operations permissions."],
            "confidence": 0.88,
            "freshnessStatus": "fresh",
            "workItemDNA": {
                "version": 3,
                "businessGoals": ["Faster fault triage"],
                "businessOutcome": "Operators can triage critical events faster.",
                "capability": "Critical Fault Detection",
            },
        }

        package = build_execution_package_v2(
            story=story,
            selected_task=task,
            acceptance_criteria=["Fault event details show severity and device health."],
            context_capsule=capsule,
            generated_tasks=[task],
            task_plan={"diagnostics": {"generated_task_count": 1}},
            readiness={"score": 86, "breakdown": {"requirements": "ready"}},
            profile={"development_standards": {"security_requirements": ["Role-based access"]}},
            validation_report={"score": 90, "status": "Approved"},
        )

        self.assertEqual(package["taskId"], 91)
        self.assertEqual(package["artifactId"], 91)
        self.assertEqual(package["artifactType"], "Task")
        self.assertEqual(package["storyId"], 42)
        self.assertEqual(package["featureId"], 21)
        self.assertEqual(package["epicId"], 7)
        self.assertEqual(package["dnaVersion"], 3)
        self.assertEqual(package["businessContext"]["featureCapability"], "Critical Fault Detection")
        self.assertEqual(package["implementationBoundary"]["allowedModules"], ["Fault Monitoring", "Telemetry"])
        self.assertEqual(package["implementationBoundary"]["blockedModules"], ["Firmware Management"])
        self.assertEqual(package["acceptanceMapping"][0]["acceptanceCriteriaId"], "AC001")
        self.assertEqual(package["repositoryContext"]["relevantFiles"][0]["name"], "src/fault/FaultEventController.cs")
        self.assertGreaterEqual(package["readiness"]["executionReadinessScore"], 80)
        self.assertEqual(package["readiness"]["status"], "Ready")

    def test_missing_file_ranking_is_explicit_and_does_not_invent_files(self) -> None:
        package = build_execution_package_v2(
            story={"id": "story-1", "title": "Start outage investigation"},
            selected_task={"id": "task-1", "title": "Add investigation entry point"},
            acceptance_criteria=["Investigation starts from a fault event."],
            context_capsule={
                "capsuleId": "execution_no_files",
                "capsuleType": "execution",
                "knowledgeVersion": "kv-1",
                "repositorySnapshotVersion": "rs-1",
                "selectedModules": ["Fault Monitoring"],
                "selectedFlows": ["Outage Investigation Flow"],
                "relevantFiles": [],
                "fileRankingStatus": "Repository file ranking not available",
                "confidence": 0.75,
            },
        )

        self.assertEqual(package["repositoryContext"]["relevantFiles"], [])
        self.assertEqual(package["repositoryContext"]["fileRankingStatus"], "Repository file ranking not available")
        self.assertIn("Repository file ranking not available", package["implementationBoundary"]["assumptions"])
        self.assertEqual(package["readiness"]["repositoryMode"], "Knowledge Snapshot")
        self.assertEqual(package["readiness"]["status"], "NeedsReview")

    def test_project_intelligence_execution_context_exposes_v2_package(self) -> None:
        profile = {
            "project_name": "LineDefender",
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry", "Firmware Management"],
                "flows": ["Fault Event Review Flow", "Firmware Rollout Flow"],
                "ranked_files": [
                    {
                        "path": "src/fault/FaultEventViewModel.cs",
                        "confidence": 0.91,
                        "reason": "Fault Monitoring detail file.",
                        "evidence": "Fault event details are rendered here.",
                    }
                ],
            },
        }
        story = {
            "id": "story-v2",
            "title": "Open critical fault event details",
            "description": "As an Operations User, I want to open critical fault event details.",
            "acceptance_criteria": ["Fault event details show severity and device health."],
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            context = ProjectIntelligenceService().build_execution_context(
                story,
                profile,
                options={"force_provider": "deterministic_fallback"},
            )

        package = context["execution_package_v2"]
        self.assertEqual(package, context["executionPackageV2"])
        self.assertEqual(package["repositoryContext"]["relevantFiles"][0]["name"], "src/fault/FaultEventViewModel.cs")
        self.assertIn("Fault Monitoring", package["implementationBoundary"]["allowedModules"])
        self.assertNotIn("Firmware Management", package["implementationBoundary"]["allowedModules"])
        self.assertEqual(package["acceptanceMapping"][0]["acceptanceCriteriaId"], "AC001")
        self.assertIn(package["readiness"]["status"], {"Ready", "NeedsReview"})

    def test_story_execution_package_uses_story_as_executable_artifact(self) -> None:
        story = {
            "id": 42,
            "feature_id": 21,
            "epic_id": 7,
            "type": "Story",
            "title": "Open critical fault event details",
            "description": "As an Operations User, I want to open critical fault event details.",
        }
        package = build_execution_package_v2(
            story=story,
            selected_task={},
            acceptance_criteria=["Fault event details show severity and device health."],
            context_capsule={
                "capsuleId": "execution_story",
                "capsuleType": "execution",
                "sourceWorkItemId": 42,
                "parentStoryId": 42,
                "knowledgeVersion": "kv-1",
                "repositorySnapshotVersion": "rs-1",
                "selectedModules": ["Fault Monitoring"],
                "selectedFlows": ["Fault Event Review Flow"],
                "selectedApplications": ["Operations Dashboard"],
                "acceptanceCriteria": ["Fault event details show severity and device health."],
                "relevantFiles": [],
                "fileRankingStatus": "Repository file ranking not available",
                "confidence": 0.75,
            },
        )

        self.assertEqual(package["artifactType"], "Story")
        self.assertEqual(package["artifactId"], 42)
        self.assertIsNone(package["taskId"])
        self.assertEqual(package["storyId"], 42)
        self.assertEqual(package["businessContext"]["storyTitle"], "Open Critical Fault Event Details")
        self.assertEqual(
            package["businessContext"]["taskObjective"],
            "Implement critical fault detail retrieval so Operations Users can assess device condition and outage impact quickly.",
        )

    def test_title_and_user_story_are_normalized_for_execution_package(self) -> None:
        package = build_execution_package_v2(
            story={
                "id": "story-weak",
                "title": "Use classify severity",
                "description": "As a Operations User, I want to use classify severity so that the user can complete classify severity as an independent outcome.",
            },
            selected_task={},
            acceptance_criteria=["Severity is displayed."],
            context_capsule={
                "capsuleId": "execution_story",
                "knowledgeVersion": "kv-1",
                "repositorySnapshotVersion": "rs-1",
                "selectedModules": ["Fault Monitoring", "Telemetry"],
                "selectedFlows": ["Fault Event Review Flow"],
                "confidence": 0.82,
            },
        )

        self.assertEqual(package["businessContext"]["storyTitle"], "Classify Fault Severity")
        self.assertIn("fault events classified by severity", package["businessContext"]["storyUserGoal"])

    def test_fragmented_acceptance_criteria_are_merged(self) -> None:
        package = build_execution_package_v2(
            story={"id": "story-fields", "title": "View detect fault"},
            selected_task={},
            acceptance_criteria=["The list shows Device ID", "Fault Type", "Severity", "Timestamp", "and Status for each event."],
            context_capsule={
                "capsuleId": "execution_fields",
                "knowledgeVersion": "kv-1",
                "repositorySnapshotVersion": "rs-1",
                "selectedModules": ["Fault Monitoring"],
                "selectedFlows": ["Fault Event Review Flow"],
                "confidence": 0.82,
            },
        )

        self.assertEqual(
            package["acceptanceMapping"][0]["acceptanceText"],
            "The fault event list displays Device ID, Fault Type, Severity, Timestamp, and Status for each event.",
        )

    def test_mashed_acceptance_criteria_are_split(self) -> None:
        package = build_execution_package_v2(
            story={"id": "story-split", "title": "View detect fault"},
            selected_task={},
            acceptance_criteria=["Fault events are sorted by Severity and Timestamp. Events refresh without duplicates."],
            context_capsule={
                "capsuleId": "execution_split",
                "knowledgeVersion": "kv-1",
                "repositorySnapshotVersion": "rs-1",
                "selectedModules": ["Fault Monitoring"],
                "selectedFlows": ["Fault Event Review Flow"],
                "confidence": 0.82,
            },
        )

        self.assertEqual(len(package["acceptanceMapping"]), 2)
        self.assertEqual(package["acceptanceMapping"][1]["acceptanceText"], "Events refresh without duplicates.")

    def test_fragmented_acceptance_criteria_force_needs_review(self) -> None:
        package = build_execution_package_v2(
            story={"id": "story-bad-ac", "title": "View detect fault"},
            selected_task={},
            acceptance_criteria=["and Status for each event."],
            context_capsule={
                "capsuleId": "execution_bad_ac",
                "knowledgeVersion": "kv-1",
                "repositorySnapshotVersion": "rs-1",
                "selectedModules": ["Fault Monitoring"],
                "selectedFlows": ["Fault Event Review Flow"],
                "confidence": 0.82,
            },
        )

        self.assertEqual(package["readiness"]["status"], "NeedsReview")
        self.assertIn("Acceptance criteria require cleanup before implementation.", package["readiness"]["warnings"])

    def test_irrelevant_login_and_device_registration_flows_are_excluded(self) -> None:
        package = build_execution_package_v2(
            story={"id": "story-tight", "title": "Classify Fault Severity"},
            selected_task={},
            acceptance_criteria=["Fault events are sorted by Severity and Timestamp."],
            context_capsule={
                "capsuleId": "execution_tight",
                "knowledgeVersion": "kv-1",
                "repositorySnapshotVersion": "rs-1",
                "selectedModules": ["Fault Monitoring", "Telemetry", "Device Management"],
                "selectedFlows": ["Fault Event Review Flow", "Login Flow", "Device Registration Flow"],
                "confidence": 0.82,
            },
        )

        self.assertEqual(package["implementationBoundary"]["allowedModules"], ["Fault Monitoring", "Telemetry"])
        self.assertEqual(package["implementationBoundary"]["allowedFlows"], ["Fault Event Review Flow"])
        self.assertIn("Device Management", package["implementationBoundary"]["blockedModules"])
        self.assertIn("Login Flow", package["implementationBoundary"]["blockedFlows"])
        self.assertIn("Device Registration Flow", package["implementationBoundary"]["blockedFlows"])


if __name__ == "__main__":
    unittest.main()
