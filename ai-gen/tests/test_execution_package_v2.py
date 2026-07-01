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
        self.assertIn(package["readiness"]["status"], {"Ready", "Needs Review"})


if __name__ == "__main__":
    unittest.main()
