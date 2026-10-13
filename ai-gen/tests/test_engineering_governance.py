import tempfile
import unittest
from pathlib import Path

from backend.governance import GovernanceEngine


class EngineeringGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = GovernanceEngine(Path(self.tmp.name) / "governance.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_policy_enforcement_blocks_unapproved_story_execution(self):
        result = self.engine.enforce_policies(
            {"artifactType": "Story", "status": "Draft", "title": "Review Fault Details"},
            {"operation": "Open Execution"},
        )

        self.assertFalse(result["compliant"])
        self.assertEqual(result["status"], "Blocked")
        self.assertIn("Story requires approval", result["violations"][0]["message"])

    def test_approval_workflow_records_audit_event(self):
        requested = self.engine.request_approval(
            {"artifactType": "Feature", "artifactId": "28", "artifactTitle": "Critical Fault Detection"},
            "Rathiesh",
        )["approval"]
        updated = self.engine.update_approval(requested["id"], "Approved", "Admin", "Ready")["approval"]
        audit = self.engine.audit_timeline()

        self.assertEqual(updated["status"], "Approved")
        self.assertEqual(audit["count"], 2)
        self.assertEqual(audit["events"][-1]["what"], "Approval Approved")

    def test_compliance_calculation_uses_policy_findings_and_quality_scores(self):
        result = self.engine.validate_compliance(
            {"artifactType": "Story", "status": "Approved"},
            {
                "repositoryConfidence": 92,
                "qa": {"acceptanceCoverage": 88},
                "securityCompliance": 90,
                "codingStandardsCompliance": 91,
            },
        )

        self.assertEqual(result["status"], "Compliant")
        self.assertGreaterEqual(result["score"], 80)

    def test_metrics_observability_feedback_and_scorecard_are_aggregated(self):
        self.engine.record_metric({"name": "Average Coverage", "category": "QA", "value": 91})
        self.engine.record_metric({"name": "Memory Reuse", "category": "Memory", "value": 70})
        self.engine.record_observation({
            "engine": "Planning Intelligence",
            "operation": "Generate Features",
            "status": "success",
            "durationMs": 1200,
            "provider": "azure_phi",
            "model": "Phi-4",
            "tokenUsage": {"prompt_tokens": 300, "completion_tokens": 100},
        })
        self.engine.record_feedback({
            "artifactType": "Story",
            "artifactId": "34",
            "category": "Story Quality",
            "rating": "thumbs_up",
            "comment": "Useful story breakdown.",
        })

        dashboard = self.engine.dashboard()

        self.assertEqual(dashboard["metrics"]["averageCoverage"], 91)
        self.assertEqual(dashboard["observability"]["byEngine"]["Planning Intelligence"], 1)
        self.assertEqual(dashboard["observability"]["tokenUsage"], 400)
        self.assertEqual(dashboard["feedback"]["satisfaction"], 100)
        self.assertIn(dashboard["scorecard"]["status"], {"Healthy", "Needs Attention", "At Risk"})

    def test_custom_policy_can_be_saved_and_evaluated(self):
        saved = self.engine.save_policy({
            "id": "repo-confidence",
            "name": "Repository confidence gate",
            "area": "Execution",
            "rules": {"repository_confidence_threshold": 90},
        })
        result = self.engine.enforce_policies({"artifactType": "Task", "status": "Approved"}, {"repositoryConfidence": 60})

        self.assertTrue(saved["created"])
        self.assertTrue(result["compliant"])
        self.assertIn("Repository confidence", result["warnings"][0]["message"])


if __name__ == "__main__":
    unittest.main()
