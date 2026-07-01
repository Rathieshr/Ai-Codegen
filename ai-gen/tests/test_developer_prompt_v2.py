import os
import tempfile
import unittest
from unittest.mock import patch

from backend.prompt_builder import build_developer_prompt_v2, build_execution_plan
from backend.project_intelligence import ProjectIntelligenceService


def _execution_package() -> dict:
    return {
        "packageId": "execpkg_fault_details",
        "taskId": 91,
        "storyId": 42,
        "featureId": 21,
        "epicId": 7,
        "dnaVersion": 3,
        "businessContext": {
            "featureCapability": "Critical Fault Detection",
            "storyUserGoal": "As an Operations User, I want to open critical fault event details.",
            "taskObjective": "Add fault event details API",
            "businessValue": "Operators can triage critical events faster.",
        },
        "implementationBoundary": {
            "inScope": ["Expose approved fault event detail fields."],
            "outOfScope": ["Firmware rollout changes."],
            "allowedModules": ["Fault Monitoring", "Telemetry"],
            "blockedModules": ["Firmware Management"],
            "allowedFlows": ["Fault Event Review Flow"],
            "blockedFlows": ["Firmware Rollout Flow"],
            "assumptions": ["Use only context approved in the Context Capsule."],
            "constraints": ["Respect role-based access."],
        },
        "acceptanceMapping": [
            {
                "acceptanceCriteriaId": "AC001",
                "acceptanceText": "Fault event details show severity and device health.",
                "implementationArea": "Backend Work",
                "validationExpectation": "Unit + integration test.",
            }
        ],
        "repositoryContext": {
            "relevantFiles": [
                {
                    "name": "src/fault/FaultEventController.cs",
                    "type": "file",
                    "confidence": 0.91,
                    "reason": "Controller handles fault event details.",
                    "evidence": ["Fault detail endpoint."],
                    "source": "repository_intelligence",
                }
            ],
            "relevantModules": [{"name": "Fault Monitoring", "type": "module", "confidence": 0.9, "reason": "Selected module."}],
            "relevantFlows": [{"name": "Fault Event Review Flow", "type": "flow", "confidence": 0.9, "reason": "Selected flow."}],
            "fileRankingStatus": "Repository file ranking available",
        },
        "engineeringRules": [
            {"type": "security", "rule": "Role-based access", "source": "project_standards"},
            {"type": "testing", "rule": "Unit and integration tests required", "source": "project_standards"},
        ],
        "risks": [{"type": "data", "risk": "Telemetry may be stale.", "source": "context_capsule"}],
        "suggestedTests": [
            {"type": "unit", "title": "Validate fault event detail mapping", "coverage": ["AC001"], "priority": "High"},
            {"type": "permission", "title": "Reject unauthorized access", "coverage": ["AC001"], "priority": "High"},
        ],
        "readiness": {"status": "Ready", "executionReadinessScore": 88},
        "diagnostics": {"rejectedContext": [{"type": "module", "name": "Firmware Management", "reason": "No firmware intent."}]},
    }


class DeveloperPromptV2Tests(unittest.TestCase):
    def test_developer_prompt_uses_execution_package_sections(self) -> None:
        result = build_developer_prompt_v2(_execution_package(), provider="azure_phi")

        prompt = result["finalPrompt"]
        self.assertEqual(result["packageId"], "execpkg_fault_details")
        self.assertIn("## Role", prompt)
        self.assertIn("## Acceptance Criteria Mapping", prompt)
        self.assertIn("AC001", prompt)
        self.assertIn("src/fault/FaultEventController.cs", prompt)
        self.assertIn("Role-based access", prompt)
        self.assertIn("Do not create fake services", prompt)
        self.assertIn("Do not modify Firmware Management", prompt)
        self.assertGreater(result["estimatedTokens"], 0)
        self.assertIn("finalPromptTokens", result["diagnostics"])

    def test_developer_prompt_does_not_invent_files_when_ranking_missing(self) -> None:
        package = _execution_package()
        package["repositoryContext"]["relevantFiles"] = []
        package["repositoryContext"]["fileRankingStatus"] = "Repository file ranking not available"

        result = build_developer_prompt_v2(package, provider="azure_phi")

        self.assertIn("Repository file ranking not available. Do not invent file paths.", result["finalPrompt"])
        self.assertEqual(result["warnings"][0], "Repository file ranking not available. Do not invent file paths.")
        self.assertNotIn("src/generated", result["finalPrompt"])

    def test_project_intelligence_build_dev_prompt_returns_v2_prompt(self) -> None:
        profile = {
            "project_name": "LineDefender",
            "development_standards": {"security_requirements": ["Role-based access"]},
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry", "Firmware Management"],
                "flows": ["Fault Event Review Flow", "Firmware Rollout Flow"],
                "ranked_files": [
                    {
                        "path": "src/fault/FaultEventViewModel.cs",
                        "confidence": 0.91,
                        "reason": "Fault detail UI file.",
                        "evidence": "Fault details are rendered here.",
                    }
                ],
            },
        }
        story = {
            "id": "story-dev-v2",
            "title": "Open critical fault event details",
            "description": "As an Operations User, I want to open critical fault event details.",
            "acceptance_criteria": ["Fault event details show severity and device health."],
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            result = ProjectIntelligenceService().build_dev_prompt(story, profile)

        self.assertIn("developer_prompt_v2", result)
        self.assertIn("execution_package_v2", result)
        self.assertEqual(result["prompt"], result["developer_prompt_v2"]["finalPrompt"])
        self.assertIn("Developer Prompt V2", result["prompt"])
        self.assertIn("Fault Event Review Flow", result["prompt"])
        self.assertNotIn("Firmware Rollout Flow", result["prompt"])
        self.assertEqual(result["provider_used"], "deterministic_execution")

    def test_execution_plan_uses_execution_package_and_mode(self) -> None:
        result = build_execution_plan(_execution_package(), execution_mode="bug_fix", provider="azure_phi")

        plan = result["plan"]
        self.assertEqual(result["packageId"], "execpkg_fault_details")
        self.assertEqual(result["executionMode"], "bug_fix")
        self.assertIn("# Execution Plan", plan)
        self.assertIn("Mode: Bug Fix", plan)
        self.assertIn("Identify root cause before editing", plan)
        self.assertIn("Fault Event Review Flow", plan)
        self.assertIn("Repository file ranking", plan)
        self.assertNotIn("Copilot", plan)
        self.assertGreater(result["estimatedTokens"], 0)
        self.assertIn("finalPlanTokens", result["diagnostics"])

    def test_execution_plan_review_mode_avoids_broad_changes(self) -> None:
        result = build_execution_plan(_execution_package(), execution_mode="review_existing_code", provider="azure_phi")

        self.assertIn("Review first", result["plan"])
        self.assertIn("Report alignment, gaps, and risks", result["plan"])
        self.assertIn("Do not regenerate planning content", result["plan"])

    def test_project_intelligence_build_execution_plan_returns_primary_plan(self) -> None:
        profile = {
            "project_name": "LineDefender",
            "development_standards": {"security_requirements": ["Role-based access"]},
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry", "Firmware Management"],
                "flows": ["Fault Event Review Flow", "Firmware Rollout Flow"],
                "ranked_files": [
                    {
                        "path": "src/fault/FaultEventViewModel.cs",
                        "confidence": 0.91,
                        "reason": "Fault detail UI file.",
                        "evidence": "Fault details are rendered here.",
                    }
                ],
            },
        }
        story = {
            "id": "story-exec-plan",
            "title": "Open critical fault event details",
            "description": "As an Operations User, I want to open critical fault event details.",
            "acceptance_criteria": ["Fault event details show severity and device health."],
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            result = ProjectIntelligenceService().build_execution_plan(story, profile, options={"execution_mode": "refactor"})

        self.assertIn("execution_plan", result)
        self.assertIn("execution_package_v2", result)
        self.assertEqual(result["plan"], result["execution_plan"]["finalPlan"])
        self.assertEqual(result["executionMode"], "refactor")
        self.assertIn("Mode: Refactor", result["plan"])
        self.assertNotIn("Copilot", result["plan"])
        self.assertEqual(result["provider_used"], "deterministic_execution")


if __name__ == "__main__":
    unittest.main()
