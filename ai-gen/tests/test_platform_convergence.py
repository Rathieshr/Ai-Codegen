from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.convergence import ConsumerRequest, ExecutionPackageConsumerService
from backend.execution import ExecutionPackageBuilder, ExecutionRequest
from backend.platform import PlatformFoundation


def package():
    capsule = {"requestId": "ctx-converge", "capsuleVersion": "3.1", "correlationId": "corr-converge", "confidence": .9, "freshnessStatus": "Fresh", "acceptanceCriteria": ["Authorized users can view details."], "diagnostics": {"repositoryMode": "CodeIndexed"}, "selectedContext": [{"sourceType": "Planning", "category": "Planning", "title": "View details", "content": "View details", "confidenceScore": .9}, {"sourceType": "Repository", "category": "File", "title": "src/Details.cs", "content": "direct", "confidenceScore": .9}, {"sourceType": "EngineeringMemory", "category": "Memory", "title": "Reusable detail pattern", "content": "pattern", "confidenceScore": .8}]}
    return ExecutionPackageBuilder().build(capsule, ExecutionRequest("ImplementationPackage", story_id="story-1"))


class PlatformConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.platform = PlatformFoundation(Path(self.temp.name) / "platform")
        self.service = ExecutionPackageConsumerService(self.platform)

    def tearDown(self): self.temp.cleanup()

    def test_developer_prompt_consumes_execution_package(self):
        result = self.service.consume(ConsumerRequest("DeveloperPrompt", package(), correlation_id="corr-1"))
        self.assertTrue(result["finalPrompt"])
        self.assertEqual(result["consumerDiagnostics"]["correlationId"], "corr-1")

    def test_qa_consumes_package_and_returns_converged_guidance(self):
        result = self.service.consume(ConsumerRequest("QA", package(), correlation_id="corr-2"))
        self.assertEqual(result["contextSource"], "ExecutionPackage")
        self.assertTrue(result["negativeTests"])
        self.assertIn("coverageExpectations", result)

    def test_validation_consumes_package_plus_runtime_evidence(self):
        result = self.service.consume(ConsumerRequest("Validation", package(), runtime_evidence={"changedFiles": ["src/Details.cs"]}, correlation_id="corr-3"))
        self.assertIn("consumerDiagnostics", result)
        self.assertEqual(result["consumerDiagnostics"]["executionPackageVersion"], "2.0")

    def test_memory_capture_does_not_rebuild_context(self):
        result = self.service.consume(ConsumerRequest("MemoryCapture", package(), runtime_evidence={"validationResult": {"status": "Approved"}}, correlation_id="corr-4"))
        self.assertFalse(result["contextRebuilt"])
        self.assertEqual(result["sourcePackageId"], package()["packageId"])

    def test_agent_runtime_receives_only_package_context_and_mode(self):
        result = self.service.consume(ConsumerRequest("AgentRuntime", package(), agent_context={"actor": "developer"}, execution_mode="BugFix", correlation_id="corr-5"))
        self.assertEqual(set(result) - {"consumerDiagnostics"}, {"executionPackage", "agentContext", "executionMode"})
        self.assertEqual(result["executionMode"], "BugFix")

    def test_vscode_payload_is_single_package_projection(self):
        result = self.service.consume(ConsumerRequest("VSCode", package(), correlation_id="corr-6"))
        self.assertEqual(result["suggestedFiles"], ["src/Details.cs"])
        self.assertIn("validation", result)
        self.assertIn("qa", result)

    def test_events_activity_and_audit_are_recorded(self):
        self.service.consume(ConsumerRequest("QA", package(), correlation_id="corr-events"))
        self.assertGreater(self.platform.events.list_recent(event_type="ExecutionPackageConsumed")["count"], 0)
        self.assertGreater(self.platform.activity.list_recent(activityType="ExecutionPackageConsumed")["count"], 0)
        self.assertGreater(self.platform.audit.by_correlation("corr-events")["count"], 0)

    def test_migrated_modules_do_not_import_context_authorities(self):
        root = Path(__file__).parents[1]
        forbidden = ("repository_intelligence", "EngineeringMemoryEngine", "MemoryContextBuilder", "project_intelligence", "context_orchestration.sources")
        for relative in ("backend/convergence", "backend/prompt_builder/developer_prompt_v2.py"):
            paths = (root / relative).rglob("*.py") if (root / relative).is_dir() else [root / relative]
            for path in paths:
                text = path.read_text(encoding="utf-8")
                for marker in forbidden: self.assertNotIn(marker, text, f"{path} independently references {marker}")


if __name__ == "__main__": unittest.main()
