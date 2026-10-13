import unittest

from backend.project_intelligence import ProjectIntelligenceService
from backend.qa import QAWorkspaceService


def _execution_package() -> dict:
    return {
        "packageId": "execpkg_fault_details",
        "taskId": 91,
        "storyId": 42,
        "businessContext": {
            "storyTitle": "Open Critical Fault Event Details",
            "storyUserGoal": "As an Operations User, I want to open critical fault event details.",
            "taskObjective": "Add fault event details API and UI state.",
            "businessValue": "Operators can triage critical events faster.",
        },
        "acceptanceMapping": [
            {
                "acceptanceCriteriaId": "AC001",
                "acceptanceText": "Operator can open a critical fault event from the event list.",
                "implementationArea": "Backend API and UI",
                "validationExpectation": "Functional and integration tests.",
            },
            {
                "acceptanceCriteriaId": "AC002",
                "acceptanceText": "Unauthorized users cannot view restricted fault event details.",
                "implementationArea": "Permission",
                "validationExpectation": "Permission tests.",
            },
        ],
        "repositoryContext": {
            "relevantModules": [{"name": "Fault Monitoring"}, {"name": "Telemetry"}],
            "relevantFlows": [{"name": "Fault Event Review Flow"}],
            "relevantServices": [{"name": "Fault Event Service"}],
            "relevantAPIs": [{"name": "Fault Event Details API"}],
            "relevantFiles": [{"name": "src/fault/FaultEventController.cs"}],
        },
        "readiness": {"status": "Ready", "executionReadinessScore": 90},
    }


class QAIntelligenceTests(unittest.TestCase):
    def test_acceptance_mapping_reports_coverage(self) -> None:
        artifact = QAWorkspaceService().evaluate(
            story={"title": "Open Critical Fault Event Details"},
            acceptance_criteria=[
                "Operator can open a critical fault event from the event list.",
                "Unauthorized users cannot view restricted fault event details.",
            ],
            execution_package=_execution_package(),
        )

        coverage = artifact["acceptanceCoverage"]
        self.assertGreaterEqual(coverage["coveragePercent"], 75)
        self.assertEqual(len(coverage["acceptanceCriteria"]), 2)
        self.assertTrue(coverage["acceptanceCriteria"][0]["mappedTests"])

    def test_regression_detection_uses_repository_context(self) -> None:
        artifact = QAWorkspaceService().evaluate(
            story={"title": "Open Critical Fault Event Details"},
            acceptance_criteria=["Operator can open a critical fault event from the event list."],
            execution_package=_execution_package(),
        )

        regression = artifact["regressionIntelligence"]
        self.assertIn("Fault Monitoring", regression["changedModules"])
        self.assertIn("Fault Event Details API", regression["affectedAPIs"])
        self.assertIn("Fault Event Review Flow", regression["potentialRegressionAreas"])

    def test_risk_and_gap_analysis_drive_readiness(self) -> None:
        artifact = QAWorkspaceService().evaluate(
            story={"title": "Open Critical Fault Event Details"},
            acceptance_criteria=[
                "Unauthorized users cannot view restricted fault event details.",
                "External regulator receives a signed report within one business day.",
            ],
            execution_package=_execution_package(),
            tests=[],
            implementation_validation={"status": "NeedsReview", "acceptanceCoverageScore": 40, "testCoverageScore": 50},
        )

        gaps = artifact["testGapAnalysis"]
        readiness = artifact["qaReadiness"]
        release = artifact["releaseRecommendation"]
        self.assertTrue(gaps["untestedAcceptanceCriteria"])
        self.assertIn(readiness["status"], {"Blocked", "Needs Review"})
        self.assertIn(release["recommendation"], {"Blocked", "Needs More Testing", "Ready With Warnings"})

    def test_project_intelligence_qa_response_contains_release_readiness(self) -> None:
        story = {
            "title": "Open Critical Fault Event Details",
            "description": "As an Operations User, I want to open critical fault event details.",
            "acceptance_criteria": [
                "Operator can open a critical fault event from the event list.",
                "Unauthorized users cannot view restricted fault event details.",
            ],
        }
        profile = {
            "project_name": "LineDefender",
            "domain": "Utility Grid Management",
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry"],
                "flows": ["Fault Event Review Flow"],
            },
        }

        result = ProjectIntelligenceService().generate_qa_test_cases(
            story,
            profile,
            execution_package=_execution_package(),
            implementation_validation={"status": "Passed", "acceptanceCoverageScore": 90, "testCoverageScore": 85},
            options={"force_provider": "deterministic_fallback"},
        )

        self.assertIn("qa_intelligence", result)
        self.assertIn("qa_readiness", result)
        self.assertIn("release_recommendation", result)
        self.assertIn(result["release_status"], {"Ready For Release", "Ready With Warnings", "Needs More Testing", "Blocked"})

    def test_generate_missing_tests_appends_gap_filling_cases(self) -> None:
        story = {
            "title": "Open Critical Fault Event Details",
            "description": "As an Operations User, I want to open critical fault event details.",
            "acceptance_criteria": [
                "Operator can open a critical fault event from the event list.",
                "Unauthorized users cannot view restricted fault event details.",
            ],
        }
        profile = {
            "project_name": "LineDefender",
            "domain": "Utility Grid Management",
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry"],
                "flows": ["Fault Event Review Flow"],
            },
        }
        existing_suite = {
            "test_suite": {
                "title": "Open Critical Fault Event Details QA Test Suite",
                "story": {"title": story["title"], "description": story["description"]},
                "test_cases": [
                    {
                        "test_id": "TC001",
                        "category": "Functional",
                        "title": "Open valid critical fault event",
                        "preconditions": ["User is signed in."],
                        "steps": ["Open the event list.", "Select a critical fault event."],
                        "expected_result": "Event details are displayed.",
                    }
                ],
            },
            "coverage_score": 40,
            "coverage_gaps": ["Unauthorized users cannot view restricted fault event details."],
        }

        result = ProjectIntelligenceService().generate_qa_test_cases(
            story,
            profile,
            execution_package=_execution_package(),
            implementation_validation={"status": "Passed", "acceptanceCoverageScore": 90, "testCoverageScore": 85},
            options={
                "force_provider": "deterministic_fallback",
                "qa_action": "generate_missing_tests",
                "existing_test_suite": existing_suite,
            },
        )

        self.assertGreater(result["generated_test_count"], 1)
        self.assertIn("gap_fill_summary", result)
        self.assertGreater(result["gap_fill_summary"]["generated_missing_tests"], 0)
        joined_titles = " ".join(test["title"] for test in result["test_suite"]["test_cases"])
        self.assertIn("acceptance criterion", joined_titles.lower())


if __name__ == "__main__":
    unittest.main()
