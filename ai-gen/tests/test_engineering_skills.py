import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.project_intelligence import ProjectIntelligenceService
from backend.skills import SkillEngine


def _execution_package() -> dict:
    return {
        "packageId": "execpkg_fault_api",
        "taskId": 51,
        "storyId": 34,
        "artifactType": "Execution Package",
        "businessContext": {
            "featureCapability": "Critical Fault Detection",
            "storyUserGoal": "Operations user reviews critical fault event details.",
            "taskObjective": "Add fault event details API and permission handling.",
        },
        "implementationBoundary": {
            "allowedModules": ["Fault Monitoring", "Telemetry"],
            "allowedFlows": ["Fault Event Review Flow"],
            "constraints": ["Role-based access required."],
        },
        "acceptanceMapping": [
            {
                "acceptanceCriteriaId": "AC001",
                "acceptanceText": "Authorized operations user can view fault severity and device health.",
                "implementationArea": "Backend API",
                "validationExpectation": "API integration and permission tests.",
            }
        ],
        "repositoryContext": {
            "relevantModules": [{"name": "Fault Monitoring"}],
            "relevantFlows": [{"name": "Fault Event Review Flow"}],
            "relevantFiles": [
                {
                    "path": "src/fault/FaultEventController.cs",
                    "type": "Controller",
                    "reason": "Handles fault event details endpoint.",
                }
            ],
        },
        "engineeringRules": [{"rule": "Authorization required"}, {"rule": "Unit and integration tests required"}],
        "risks": [{"risk": "Telemetry may be unavailable."}],
        "suggestedTests": [{"type": "permission", "title": "Reject unauthorized fault access"}],
    }


class EngineeringSkillsTests(unittest.TestCase):
    def test_resolves_single_backend_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            result = engine.resolve(_execution_package())

        names = [skill["name"] for skill in result["recommendedSkills"]]
        self.assertIn("REST API", names)
        self.assertGreater(result["matchCount"], 0)

    def test_resolves_multiple_skills_from_execution_context(self) -> None:
        package = _execution_package()
        package["businessContext"]["taskObjective"] = "Create searchable telemetry dashboard grid with permission checks."
        package["repositoryContext"]["relevantFiles"].append({"path": "src/ui/FaultGrid.tsx", "type": "Grid"})

        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            result = engine.resolve(package)

        names = {skill["name"] for skill in result["recommendedSkills"]}
        self.assertIn("React Grid", names)
        self.assertIn("Telemetry Dashboard", names)
        self.assertIn("Permission Matrix", names)

    def test_versions_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            before = next(skill for skill in engine.list_skills()["skills"] if skill["id"] == "skill_rest_api")
            after = engine.version_skill("skill_rest_api", {"description": "Updated REST API skill."})

        self.assertEqual(after["version"], before["version"] + 1)
        self.assertEqual(after["description"], "Updated REST API skill.")

    def test_skill_composition_contains_guidance_and_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            result = engine.compose(_execution_package())

        self.assertTrue(result["skills"])
        self.assertIn("implementationGuidance", result["composition"])
        self.assertIn("testTemplates", result["composition"])
        self.assertTrue(result["composition"]["testTemplates"])

    def test_skill_discovery_for_execution_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            result = engine.discover("execution", {"artifactType": "Task"}, {"artifactType": "Task"})

        self.assertGreater(result["count"], 0)
        self.assertIn("Execution", result["groupedSkills"])
        self.assertTrue(any(skill["name"] == "Build Execution Package" for skill in result["availableSkills"]))

    def test_skill_execution_respects_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            blocked = engine.execute("skill_build_execution_package", {"artifact": {"title": "Build Fault API"}, "workspace": "execution", "permissions": []})

        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("missing permissions", ", ".join(blocked["policy"]["reasons"]))

    def test_skill_execution_records_history_and_uses_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            result = engine.execute(
                "skill_build_execution_package",
                {
                    "artifact": {"title": "Build Fault API"},
                    "workspace": "execution",
                    "permissions": ["execute_skills"],
                    "agentId": "execution",
                    "repositoryIntelligence": {"relevantFiles": [{"path": "src/fault/FaultEventController.cs"}]},
                    "knowledgeRegistry": {"modules": ["Fault Monitoring"], "flows": ["Fault Event Review Flow"]},
                },
            )
            history = engine.history()

        self.assertEqual(result["status"], "success")
        self.assertIn("selectedFiles", result["result"]["output"])
        self.assertEqual(history["count"], 1)
        self.assertEqual(history["events"][0]["skillId"], "skill_build_execution_package")

    def test_skill_library_groups_by_workflow_area(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            skills = engine.list_skills()

        self.assertIn("groupedSkills", skills)
        self.assertIn("Planning", skills["groupedSkills"])
        self.assertIn("Execution", skills["groupedSkills"])
        self.assertIn("QA", skills["groupedSkills"])

    def test_execution_plan_is_enriched_with_skills(self) -> None:
        profile = {
            "project_name": "LineDefender",
            "development_standards": {"security_requirements": ["Role-based access"]},
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry"],
                "flows": ["Fault Event Review Flow"],
                "ranked_files": [
                    {
                        "path": "src/fault/FaultEventController.cs",
                        "confidence": 0.91,
                        "reason": "Fault detail endpoint.",
                    }
                ],
            },
        }
        story = {
            "id": "story-skills",
            "title": "Open critical fault event details",
            "description": "As an Operations User, I want to open critical fault event details.",
            "acceptance_criteria": ["Authorized operations user can view severity and device health."],
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            result = ProjectIntelligenceService().build_execution_plan(story, profile)

        self.assertIn("engineering_skills", result)
        self.assertTrue(result["engineering_skills"])
        self.assertIn("## Engineering Skills", result["plan"])
        self.assertIn("skillComposition", result["execution_plan"])

    def test_skill_diagnostics_include_execution_history_and_success_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = SkillEngine(Path(temp_dir) / "skills.json")
            engine.execute(
                "skill_build_execution_package",
                {
                    "artifact": {"title": "Build Fault API"},
                    "workspace": "execution",
                    "permissions": ["execute_skills"],
                    "agentId": "execution",
                },
            )
            diagnostics = engine.diagnostics_summary()

        self.assertIn("executionEvents", diagnostics)
        self.assertIn("successRate", diagnostics)
        self.assertEqual(diagnostics["executionEvents"], 1)


if __name__ == "__main__":
    unittest.main()
