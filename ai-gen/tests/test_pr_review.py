import unittest
from unittest.mock import patch

from backend.pr_review import PRReviewEngine
from backend.project_intelligence import ProjectIntelligenceService
from tests.test_implementation_validation import _aligned_files, _execution_package


def _pull_request() -> dict:
    return {
        "id": 501,
        "title": "Add fault event details endpoint",
        "linkedWorkItems": [{"id": 42, "type": "User Story", "title": "Open critical fault event details"}],
    }


class PRReviewTests(unittest.TestCase):
    def test_pr_review_loads_linked_work_item_and_execution_package(self) -> None:
        report = PRReviewEngine().review(
            pull_request=_pull_request(),
            execution_package=_execution_package(),
            changed_files=_aligned_files(),
            test_results={"status": "passed"},
            build_result={"status": "passed"},
        )

        self.assertEqual(report["pullRequestId"], 501)
        self.assertEqual(report["linkedWorkItems"][0]["id"], 42)
        self.assertEqual(report["implementationValidation"]["packageId"], "execpkg_fault_details")
        self.assertEqual(report["status"], "Passed")

    def test_missing_acceptance_criteria_coverage_blocks_pr(self) -> None:
        report = PRReviewEngine().review(
            pull_request=_pull_request(),
            execution_package=_execution_package(),
            changed_files=[{"path": "src/fault/FaultEventController.cs", "diff": "unrelated formatting"}],
        )

        self.assertEqual(report["status"], "Blocked")
        self.assertTrue(any("AC001" in item or "acceptance" in item.lower() for item in report["blockingIssues"]))

    def test_blocked_module_change_blocks_pr(self) -> None:
        files = _aligned_files() + [{"path": "src/firmware/FirmwareManagementService.cs", "diff": "firmware rollout"}]

        report = PRReviewEngine().review(pull_request=_pull_request(), execution_package=_execution_package(), changed_files=files)

        self.assertEqual(report["status"], "Blocked")
        self.assertTrue(any("blocked" in item.lower() or "out-of-scope" in item.lower() for item in report["blockingIssues"]))

    def test_missing_tests_creates_needs_review(self) -> None:
        report = PRReviewEngine().review(
            pull_request=_pull_request(),
            execution_package=_execution_package(),
            changed_files=[{"path": "src/fault/FaultEventController.cs", "diff": "severity device health validation authorization logger"}],
        )

        self.assertEqual(report["status"], "NeedsReview")
        self.assertLess(report["scores"]["tests"], 80)
        self.assertTrue(report["warnings"])

    def test_review_comment_is_generated(self) -> None:
        report = PRReviewEngine().review(
            pull_request=_pull_request(),
            execution_package=_execution_package(),
            changed_files=_aligned_files(),
            test_results={"status": "passed"},
        )

        self.assertIn("## HEI PR Review", report["generatedReviewComment"])
        self.assertIn("Acceptance Coverage", report["generatedReviewComment"])

    def test_posting_is_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {"ENABLE_PR_COMMENT_POSTING": "false"}, clear=False):
            result = PRReviewEngine().post_comment({"generatedReviewComment": "review"})

        self.assertFalse(result["posted"])
        self.assertTrue(result["disabled"])

    def test_no_linked_work_item_returns_needs_review_with_explanation(self) -> None:
        report = PRReviewEngine().review(
            pull_request={"id": 502, "title": "Unlinked PR"},
            execution_package=_execution_package(),
            changed_files=_aligned_files(),
        )

        self.assertEqual(report["status"], "NeedsReview")
        self.assertIn("no linked work item", report["summary"].lower())
        self.assertTrue(any("No linked Azure DevOps work item" in item for item in report["warnings"]))

    def test_project_intelligence_service_exposes_pr_review(self) -> None:
        report = ProjectIntelligenceService().review_pr(
            pull_request=_pull_request(),
            execution_package=_execution_package(),
            changed_files=_aligned_files(),
            test_results={"status": "passed"},
        )

        self.assertIn("generatedReviewComment", report)
        self.assertEqual(report["implementationValidation"]["packageId"], "execpkg_fault_details")


if __name__ == "__main__":
    unittest.main()
