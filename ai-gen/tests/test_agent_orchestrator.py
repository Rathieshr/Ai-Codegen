import tempfile
import unittest
from pathlib import Path

from backend.agents import AgentOrchestrator


class AgentOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orchestrator = AgentOrchestrator(Path(self.tmp.name) / "agents.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_story_approved_triggers_planning_agent(self):
        result = self.orchestrator.trigger({
            "eventType": "Story Approved",
            "artifactType": "Story",
            "artifactId": "34",
            "artifactTitle": "Review Critical Fault Details",
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["agent"]["name"], "Planning Agent")
        self.assertEqual(result["workflow"]["state"], "WaitingApproval")
        self.assertIn("Generate Tasks", [step["name"] for step in result["workflow"]["steps"]])
        self.assertEqual(result["workflow"]["nextAction"], "Approve Planning Output")

    def test_story_created_triggers_planning_agent(self):
        result = self.orchestrator.trigger({
            "eventType": "Story Created",
            "artifactType": "Story",
            "artifactId": "35",
            "artifactTitle": "Open Fault Details",
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["agent"]["name"], "Planning Agent")
        self.assertIn("Prepare Story", [step["name"] for step in result["workflow"]["steps"]])
        self.assertIn("Suggest Acceptance Criteria", [step["name"] for step in result["workflow"]["steps"]])

    def test_task_approved_triggers_execution_agent(self):
        result = self.orchestrator.trigger({"eventType": "Task Approved", "artifactType": "Task", "artifactId": "51"})

        self.assertEqual(result["agent"]["name"], "Execution Agent")
        self.assertIn("Build Execution Package", [step["name"] for step in result["workflow"]["steps"]])
        self.assertEqual(result["workflow"]["state"], "WaitingApproval")

    def test_story_execution_started_triggers_execution_agent(self):
        result = self.orchestrator.trigger({"eventType": "Story Execution Started", "artifactType": "Story", "artifactId": "52"})

        self.assertEqual(result["agent"]["name"], "Execution Agent")
        self.assertIn("Prepare Context Capsule", [step["name"] for step in result["workflow"]["steps"]])
        self.assertIn("Notify VS Code", [step["name"] for step in result["workflow"]["steps"]])

    def test_validation_passed_triggers_qa_agent(self):
        result = self.orchestrator.trigger({"eventType": "Implementation Validation Passed", "artifactType": "Story", "artifactId": "34"})

        self.assertEqual(result["agent"]["name"], "QA Agent")
        self.assertIn("QA Readiness", [step["name"] for step in result["workflow"]["steps"]])
        self.assertEqual(result["workflow"]["state"], "WaitingApproval")

    def test_pr_created_triggers_review_agent(self):
        result = self.orchestrator.trigger({"eventType": "PR Created", "artifactType": "Pull Request", "artifactId": "99"})

        self.assertEqual(result["agent"]["name"], "Review Agent")
        self.assertIn("Compare Against Execution Package", [step["name"] for step in result["workflow"]["steps"]])
        self.assertEqual(result["workflow"]["nextAction"], "Human Merge Decision")

    def test_approved_artifact_triggers_memory_agent(self):
        result = self.orchestrator.trigger({"eventType": "Artifact Approved", "artifactType": "Feature", "artifactId": "28"})

        self.assertEqual(result["agent"]["name"], "Memory Agent")
        self.assertIn("Store Validated Patterns", [step["name"] for step in result["workflow"]["steps"]])
        self.assertEqual(result["workflow"]["state"], "WaitingApproval")

    def test_repository_scan_triggers_repository_agent(self):
        result = self.orchestrator.trigger({"eventType": "Repository Scan", "artifactType": "Repository", "artifactId": "LineDefender"})

        self.assertEqual(result["agent"]["name"], "Repository Agent")
        self.assertIn("Refresh Repository Intelligence", [step["name"] for step in result["workflow"]["steps"]])
        self.assertIn("Update Knowledge Registry", [step["name"] for step in result["workflow"]["steps"]])

    def test_agents_stop_at_approval_checkpoint_and_resume_manually(self):
        result = self.orchestrator.trigger({"eventType": "Story Approved", "artifactType": "Story", "artifactId": "34"})
        workflow_id = result["workflow"]["id"]

        waiting = self.orchestrator.dashboard()["waitingAgents"]
        resumed = self.orchestrator.resume(workflow_id, "Rathiesh")["workflow"]

        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["currentAction"], "Wait For Human Approval")
        self.assertEqual(resumed["state"], "Completed")
        self.assertIn("Human approval received", [item["message"] for item in resumed["timeline"]])

    def test_agents_can_be_disabled_by_feature_flag(self):
        self.orchestrator.update_feature_flags({"repositoryAgent": False})
        result = self.orchestrator.trigger({"eventType": "Repository Scan", "artifactType": "Repository", "artifactId": "LineDefender"})

        self.assertFalse(result["handled"])
        self.assertIn("disabled by feature flag", result["message"])

    def test_dashboard_exposes_flags_policies_and_history(self):
        self.orchestrator.trigger({"eventType": "PR Created", "artifactType": "Pull Request", "artifactId": "99"})
        dashboard = self.orchestrator.dashboard()

        self.assertIn("featureFlags", dashboard)
        self.assertIn("policies", dashboard)
        self.assertIn("history", dashboard)
        self.assertIn("reviewAgent", dashboard["featureFlags"])
        self.assertTrue(dashboard["policies"])

    def test_unknown_trigger_is_recorded_without_workflow(self):
        result = self.orchestrator.trigger({"eventType": "Unknown Event"})

        self.assertFalse(result["handled"])
        self.assertEqual(self.orchestrator.list_events()["count"], 1)
        self.assertEqual(self.orchestrator.list_workflows()["count"], 0)


if __name__ == "__main__":
    unittest.main()
