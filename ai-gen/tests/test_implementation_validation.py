import unittest

from backend.implementation_validation import ImplementationValidationEngine
from backend.project_intelligence import ProjectIntelligenceService


def _execution_package() -> dict:
    return {
        "packageId": "execpkg_fault_details",
        "taskId": 91,
        "storyId": 42,
        "businessContext": {
            "taskObjective": "Add fault event details API",
            "storyUserGoal": "Open critical fault event details",
        },
        "implementationBoundary": {
            "inScope": ["Expose approved fault event detail fields"],
            "outOfScope": ["Firmware rollout changes"],
            "allowedModules": ["Fault Monitoring", "Telemetry"],
            "blockedModules": ["Firmware Management"],
            "allowedFlows": ["Fault Event Review Flow"],
            "blockedFlows": ["Firmware Rollout Flow"],
        },
        "acceptanceMapping": [
            {
                "acceptanceCriteriaId": "AC001",
                "acceptanceText": "Fault event details show severity and device health.",
                "implementationArea": "Fault event detail query and response mapping",
                "validationExpectation": "Unit and integration test.",
            }
        ],
        "repositoryContext": {
            "relevantFiles": [
                {
                    "name": "src/fault/FaultEventController.cs",
                    "type": "file",
                    "confidence": 0.91,
                    "reason": "Controller handles fault event details.",
                }
            ],
            "relevantModules": [{"name": "Fault Monitoring"}],
            "relevantFlows": [{"name": "Fault Event Review Flow"}],
            "fileRankingStatus": "Repository file ranking available",
        },
        "engineeringRules": [
            {"rule": "Structured logging"},
            {"rule": "Input validation"},
            {"rule": "Role-based authorization"},
            {"rule": "Unit and integration tests required"},
        ],
        "suggestedTests": [
            {"testType": "unit tests", "title": "Validate fault event mapping"},
            {"testType": "integration tests", "title": "Load fault event details"},
            {"testType": "permission tests", "title": "Reject unauthorized access"},
            {"testType": "negative tests", "title": "Handle missing event"},
            {"testType": "regression tests", "title": "Existing event review still works"},
        ],
    }


def _aligned_files() -> list[dict]:
    return [
        {
            "path": "src/fault/FaultEventController.cs",
            "diff": "Add logger, validation, authorization role check, fault event severity and device health response mapping.",
        },
        {
            "path": "tests/fault/FaultEventControllerTests.cs",
            "diff": "unit integration permission negative regression tests assert invalid event and unauthorized access.",
        },
    ]


class ImplementationValidationTests(unittest.TestCase):
    def test_validation_passes_when_changed_files_match_execution_package(self) -> None:
        report = ImplementationValidationEngine().validate(
            execution_package=_execution_package(),
            changed_files=_aligned_files(),
            test_results={"status": "passed"},
            build_result={"status": "passed"},
        )

        self.assertEqual(report["status"], "Passed")
        self.assertGreaterEqual(report["acceptanceCoverageScore"], 80)
        self.assertGreaterEqual(report["repositoryAlignmentScore"], 80)
        self.assertFalse(report["violations"])

    def test_validation_flags_blocked_module_changes(self) -> None:
        files = _aligned_files() + [{"path": "src/firmware/FirmwareManagementService.cs", "diff": "firmware rollout change"}]

        report = ImplementationValidationEngine().validate(execution_package=_execution_package(), changed_files=files)

        self.assertEqual(report["status"], "Failed")
        self.assertTrue(any(v["rule"] == "blocked_scope_modified" for v in report["violations"]))
        self.assertIn("Firmware Management", report["scopeCompliance"]["touchedBlockedScope"])

    def test_validation_flags_missing_acceptance_criteria(self) -> None:
        report = ImplementationValidationEngine().validate(
            execution_package=_execution_package(),
            changed_files=[{"path": "src/fault/FaultEventController.cs", "diff": "unrelated formatting"}],
        )

        self.assertLess(report["acceptanceCoverageScore"], 80)
        self.assertTrue(any(v["rule"] == "acceptance_criteria_coverage" for v in report["violations"]))

    def test_validation_flags_missing_tests(self) -> None:
        report = ImplementationValidationEngine().validate(
            execution_package=_execution_package(),
            changed_files=[{"path": "src/fault/FaultEventController.cs", "diff": "severity device health validation authorization logger"}],
        )

        self.assertLess(report["testCoverageScore"], 80)
        self.assertTrue(any(v["rule"] == "test_coverage" for v in report["violations"]))

    def test_validation_flags_unrelated_files(self) -> None:
        report = ImplementationValidationEngine().validate(
            execution_package=_execution_package(),
            changed_files=[{"path": "src/billing/InvoiceController.cs", "diff": "severity device health"}],
        )

        self.assertLess(report["repositoryAlignmentScore"], 80)
        self.assertTrue(any(v["rule"] == "repository_alignment" for v in report["violations"]))

    def test_validation_shows_needs_review_for_unverifiable_ac(self) -> None:
        report = ImplementationValidationEngine().validate(execution_package=_execution_package(), changed_files=[])

        self.assertEqual(report["status"], "NeedsReview")
        self.assertEqual(report["acceptanceResults"][0]["status"], "not verifiable")
        self.assertTrue(report["recommendations"])

    def test_project_intelligence_service_exposes_implementation_validation(self) -> None:
        report = ProjectIntelligenceService().validate_implementation(
            execution_package=_execution_package(),
            changed_files=_aligned_files(),
            test_results={"status": "passed"},
        )

        self.assertEqual(report["packageId"], "execpkg_fault_details")
        self.assertIn(report["status"], {"Passed", "NeedsReview"})
        self.assertIn("recommendations", report)


if __name__ == "__main__":
    unittest.main()
