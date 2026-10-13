from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.execution_runtime import (
    ExecutionRuntime,
    ExecutionRuntimeRepository,
    build_execution_runtime_router,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


def _request(**overrides) -> dict:
    value = {
        "executionPromptId": "optimizedprompt-1",
        "executionPlanVersion": "plan-v4",
        "executionPackageVersion": "package-v7",
        "repositorySnapshotVersion": "snapshot-v9",
        "provider": "Azure OpenAI",
        "model": "GPT",
        "correlationId": "corr-runtime-42",
        "developerId": "developer-7",
        "workspaceId": "workspace-gridhub",
        "branch": "feature/device-health",
        "commitBefore": "abc123",
        "runtimeContext": {
            "repositoryId": "repo-gridhub",
            "repositoryBaseline": [
                {"path": "src/DeviceHealthService.cs"},
                {"path": "tests/DeviceHealthServiceTests.cs"},
            ],
        },
    }
    value.update(overrides)
    return value


def _provider_response() -> dict:
    content = {
        "summary": "Added device health evaluation and its tests.",
        "artifacts": [
            {
                "type": "Code",
                "path": "src/DeviceHealthService.cs",
                "changeType": "Modified",
                "content": "public HealthStatus Evaluate(Device device) { return device.Health; }",
                "evidence": ["Implements the approved device health task."],
            },
            {
                "type": "Test",
                "path": "tests/DeviceHealthServiceTests.cs",
                "changeType": "Modified",
                "content": "[Fact] public void ReportsOfflineDevice() {}",
            },
        ],
    }
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 420, "completion_tokens": 170, "total_tokens": 590},
    }


class AIExecutionRuntimeFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.runtime = ExecutionRuntime(
            ExecutionRuntimeRepository(JsonMapStore(self.root / "runtime-sessions.json")),
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_execution_session_lifecycle_and_persistence(self) -> None:
        started = self.runtime.start(_request())
        self.assertEqual(started["status"], "AwaitingResponse")
        self.assertEqual(started["executionPlanVersion"], "plan-v4")
        self.assertEqual(started["executionPackageVersion"], "package-v7")
        self.assertEqual(started["repositorySnapshotVersion"], "snapshot-v9")
        self.assertEqual(started["correlationId"], "corr-runtime-42")

        completed = self.runtime.receive_response(started["sessionId"], _provider_response(), {"commitAfter": "def456"})
        self.assertEqual(completed["status"], "Completed")
        self.assertTrue(completed["completedAt"])
        self.assertEqual(completed["commitAfter"], "def456")
        self.assertEqual(self.runtime.get(started["sessionId"])["status"], "Completed")

    def test_provider_response_is_interpreted_into_artifacts_and_metadata_diff(self) -> None:
        session = self.runtime.start(_request())
        completed = self.runtime.receive_response(session["sessionId"], _provider_response())

        self.assertEqual(completed["result"]["responseType"], "ProviderEnvelope")
        self.assertEqual(completed["result"]["tokenUsage"]["total_tokens"], 590)
        self.assertEqual([item["type"] for item in completed["artifacts"]], ["Code", "Test"])
        self.assertEqual(completed["engineeringDiff"]["summary"]["modified"], 2)
        self.assertFalse(completed["engineeringDiff"]["repositoryRead"])
        self.assertFalse(completed["engineeringDiff"]["gitUsed"])

    def test_repository_comparison_never_modifies_real_files(self) -> None:
        source = self.root / "DeviceHealthService.cs"
        source.write_text("original", encoding="utf-8")
        request = _request(runtimeContext={"repositoryBaseline": [{"path": str(source)}]})
        response = {"artifacts": [{"type": "Code", "path": str(source), "changeType": "Modified", "content": "changed"}]}

        session = self.runtime.start(request)
        completed = self.runtime.receive_response(session["sessionId"], response)

        self.assertEqual(source.read_text(encoding="utf-8"), "original")
        self.assertFalse(completed["diagnostics"]["repositoryModified"])
        self.assertEqual(completed["diagnostics"]["gitOperations"], 0)
        self.assertEqual(completed["diagnostics"]["azureDevOpsWrites"], 0)
        self.assertEqual(completed["diagnostics"]["pullRequestsCreated"], 0)

    def test_downstream_work_is_recorded_but_not_invoked(self) -> None:
        session = self.runtime.start(_request())
        completed = self.runtime.receive_response(session["sessionId"], _provider_response())

        self.assertEqual(
            [item["type"] for item in completed["downstreamIntents"]],
            ["ImplementationValidation", "QAAnalysis", "EngineeringMemoryCandidate", "PRCandidate"],
        )
        self.assertTrue(all(item["invoked"] is False for item in completed["downstreamIntents"]))
        self.assertEqual(completed["diagnostics"]["downstreamServicesInvoked"], 0)
        self.assertEqual(completed["memoryCandidate"]["approvalStatus"], "Draft")
        self.assertFalse(completed["memoryCandidate"]["indexed"])
        self.assertFalse(completed["prCandidate"]["created"])

    def test_plain_text_response_is_retained_with_lower_confidence(self) -> None:
        session = self.runtime.start(_request())
        completed = self.runtime.receive_response(session["sessionId"], "Implementation completed; no structured file list was supplied.")

        self.assertEqual(completed["result"]["responseType"], "PlainText")
        self.assertIn("Implementation completed", completed["result"]["structuredResponse"]["summary"])
        self.assertEqual(completed["artifacts"], [])
        self.assertLess(completed["confidence"], 0.7)
        self.assertTrue(completed["warnings"])

    def test_failure_is_persisted_and_publishes_failure_event(self) -> None:
        session = self.runtime.start(_request())
        with self.assertRaisesRegex(ValueError, "providerResponse"):
            self.runtime.receive_response(session["sessionId"], None)

        failed = self.runtime.get(session["sessionId"])
        self.assertEqual(failed["status"], "Failed")
        self.assertTrue(failed["completedAt"])
        events = self.platform.events.list_recent(event_type="ExecutionFailed")["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["correlationId"], "corr-runtime-42")

    def test_active_session_can_be_cancelled(self) -> None:
        session = self.runtime.start(_request())
        cancelled = self.runtime.cancel(session["sessionId"], "Developer stopped the run.")

        self.assertEqual(cancelled["status"], "Cancelled")
        self.assertIn("Developer stopped the run.", cancelled["warnings"])
        self.assertEqual(self.platform.events.list_recent(event_type="ExecutionCancelled")["count"], 1)
        with self.assertRaisesRegex(ValueError, "already Cancelled"):
            self.runtime.receive_response(session["sessionId"], _provider_response())

    def test_correlation_id_survives_every_runtime_event(self) -> None:
        session = self.runtime.start(_request())
        self.runtime.receive_response(session["sessionId"], _provider_response())

        events = self.platform.events.list_recent(limit=20)["events"]
        runtime_events = [item for item in events if item["eventType"].startswith("Execution")]
        self.assertEqual(
            {item["eventType"] for item in runtime_events},
            {"ExecutionStarted", "ExecutionResponseReceived", "ExecutionInterpreted", "ExecutionCompleted"},
        )
        self.assertEqual({item["correlationId"] for item in runtime_events}, {"corr-runtime-42"})

    def test_summary_and_diagnostics_are_safe_projections(self) -> None:
        session = self.runtime.start(_request())
        self.runtime.receive_response(session["sessionId"], _provider_response())
        summary = self.runtime.summary(session["sessionId"])
        diagnostics = self.runtime.diagnostics(session["sessionId"])

        self.assertEqual(summary["artifactCount"], 2)
        self.assertNotIn("rawResponse", summary)
        self.assertEqual(diagnostics["executionPlanVersion"], "plan-v4")
        self.assertEqual(diagnostics["executionPackageVersion"], "package-v7")
        self.assertEqual(diagnostics["repositorySnapshotVersion"], "snapshot-v9")
        self.assertEqual(diagnostics["correlationId"], "corr-runtime-42")
        self.assertFalse(diagnostics["providerInvoked"])
        self.assertEqual(diagnostics["llmCalls"], 0)

    def test_api_contract_exposes_lifecycle_endpoints(self) -> None:
        router = build_execution_runtime_router(self.runtime)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(
            set(routes),
            {
                ("POST", "/execution-runtime/start"),
                ("POST", "/execution-runtime/{session_id}/response"),
                ("POST", "/execution-runtime/{session_id}/cancel"),
                ("GET", "/execution-runtime/{session_id}"),
                ("GET", "/execution-runtime/{session_id}/summary"),
                ("GET", "/execution-runtime/{session_id}/diagnostics"),
            },
        )
        session = routes[("POST", "/execution-runtime/start")](_request())
        completed = routes[("POST", "/execution-runtime/{session_id}/response")](
            session["sessionId"], {"providerResponse": _provider_response()}
        )
        self.assertEqual(completed["status"], "Completed")
        self.assertEqual(routes[("GET", "/execution-runtime/{session_id}/summary")](session["sessionId"])["artifactCount"], 2)

    def test_runtime_has_no_provider_git_ado_or_downstream_engine_imports(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "execution_runtime"
        forbidden = (
            "subprocess",
            "backend.refinement.provider",
            "backend.ado",
            "backend.repository_intelligence",
            "backend.implementation_validation",
            "backend.qa",
            "backend.engineering_memory",
            "backend.pr_review",
        )
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, source, f"{path} imports forbidden runtime authority {marker}")


if __name__ == "__main__":
    unittest.main()
