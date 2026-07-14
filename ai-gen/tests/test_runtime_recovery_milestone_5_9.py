from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.execution_runtime import (
    ExecutionRuntime,
    ExecutionRuntimeRepository,
    RuntimeObservabilityService,
    RuntimeTraceRepository,
    build_runtime_recovery_router,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


def _request(**overrides) -> dict:
    value = {
        "executionPromptId": "prompt-recovery",
        "executionPlanVersion": "plan-recovery-v1",
        "executionPackageVersion": "package-recovery-v1",
        "repositorySnapshotVersion": "snapshot-recovery-v1",
        "provider": "Azure OpenAI",
        "model": "GPT-5",
        "correlationId": "corr-recovery-59",
        "idempotencyKey": "start-recovery-59",
        "maxRetries": 2,
    }
    value.update(overrides)
    return value


def _response(summary: str = "Recovered implementation completed.") -> dict:
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "summary": summary,
            "artifacts": [{"type": "Code", "path": "src/Recovery.cs", "changeType": "Modified"}],
        })}}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
    }


class RuntimeRecoveryMilestone59Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = JsonMapStore(self.root / "runtime.json")
        self.repository = ExecutionRuntimeRepository(self.store)
        self.platform = PlatformFoundation(self.root / "platform")
        self.runtime = ExecutionRuntime(self.repository, platform=self.platform)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_provider_timeout_can_retry_and_publish_recovered(self) -> None:
        session = self.runtime.start(_request())
        timed_out = self.runtime.timeout(session["sessionId"], "Provider exceeded 30 seconds.")

        self.assertEqual(timed_out["status"], "TimedOut")
        self.assertEqual(timed_out["lastFailure"]["type"], "Timeout")
        self.assertEqual(self.platform.events.list_recent(event_type="ExecutionTimedOut")["count"], 1)

        retried = self.runtime.retry(session["sessionId"], "Retry with the same approved prompt.")
        completed = self.runtime.receive_response(
            session["sessionId"], _response(), {"responseId": "provider-response-retry-1"}
        )

        self.assertEqual(retried["status"], "AwaitingResponse")
        self.assertEqual(retried["attempt"], 2)
        self.assertEqual(completed["status"], "Completed")
        self.assertEqual(completed["recovery"]["retryCount"], 1)
        self.assertEqual(self.platform.events.list_recent(event_type="ExecutionRetried")["count"], 1)
        self.assertEqual(self.platform.events.list_recent(event_type="ExecutionRecovered")["count"], 1)

    def test_restart_loads_failed_state_and_resumes_from_checkpoint(self) -> None:
        session = self.runtime.start(_request())
        failed = self.runtime.report_failure(session["sessionId"], {
            "type": "NetworkFailure",
            "reason": "Connection reset by peer.",
            "idempotencyKey": "network-failure-1",
        })
        restarted = ExecutionRuntime(ExecutionRuntimeRepository(JsonMapStore(self.root / "runtime.json")), platform=self.platform)

        persisted = restarted.get(session["sessionId"])
        resumed = restarted.resume(session["sessionId"], "Network connectivity restored.")
        completed = restarted.receive_response(
            session["sessionId"], _response(), {"responseId": "provider-response-after-restart"}
        )

        self.assertEqual(persisted["status"], "Failed")
        self.assertEqual(persisted["lastFailure"]["type"], "NetworkFailure")
        self.assertEqual(resumed["resumeFromCheckpoint"], "NetworkFailure")
        self.assertEqual(resumed["status"], "AwaitingResponse")
        self.assertEqual(completed["status"], "Completed")
        self.assertEqual(completed["recovery"]["resumeCount"], 1)
        self.assertEqual(self.platform.events.list_recent(event_type="ExecutionResumed")["count"], 1)

    def test_duplicate_callback_is_acknowledged_without_reinterpretation(self) -> None:
        session = self.runtime.start(_request())
        first = self.runtime.receive_response(
            session["sessionId"], _response(), {"responseId": "callback-duplicate-1"}
        )
        duplicate = self.runtime.receive_response(
            session["sessionId"], _response("Conflicting duplicate body."), {"responseId": "callback-duplicate-1"}
        )

        self.assertEqual(duplicate["result"]["resultId"], first["result"]["resultId"])
        self.assertEqual(duplicate["lastResponseDisposition"], "DuplicateIgnored")
        self.assertEqual(duplicate["duplicateResponseCount"], 1)
        self.assertEqual(len(duplicate["responseHistory"]), 1)
        self.assertEqual(self.platform.events.list_recent(event_type="ExecutionDuplicateResponseIgnored")["count"], 1)
        with self.assertRaisesRegex(ValueError, "already Completed"):
            self.runtime.receive_response(session["sessionId"], _response(), {"responseId": "different-callback"})

    def test_partial_response_is_persisted_and_execution_can_resume(self) -> None:
        session = self.runtime.start(_request())
        partial = self.runtime.receive_response(
            session["sessionId"],
            {"choices": [{"finish_reason": "length", "message": {"content": "Partial implementation"}}]},
            {"responseId": "partial-1"},
        )

        self.assertEqual(partial["status"], "PartialResponse")
        self.assertEqual(partial["lastCheckpoint"], "PartialResponse")
        self.assertEqual(len(partial["partialResponses"]), 1)
        self.assertEqual(partial["result"], None)

        resumed = self.runtime.resume(session["sessionId"], "Request the remaining provider output.")
        completed = self.runtime.receive_response(
            session["sessionId"], _response(), {"responseId": "partial-final-1"}
        )

        self.assertEqual(resumed["resumeFromCheckpoint"], "PartialResponse")
        self.assertEqual(completed["status"], "Completed")
        self.assertEqual(len(completed["responseHistory"]), 2)
        self.assertEqual(completed["diagnostics"]["partialResponseCount"], 1)

    def test_provider_failure_is_persisted_and_idempotent(self) -> None:
        session = self.runtime.start(_request())
        payload = {
            "type": "ProviderFailure",
            "reason": "Provider returned 503.",
            "idempotencyKey": "provider-failure-503",
        }
        first = self.runtime.report_failure(session["sessionId"], payload)
        duplicate = self.runtime.report_failure(session["sessionId"], payload)

        self.assertEqual(first["lastFailure"]["type"], "ProviderFailure")
        self.assertEqual(duplicate["lastOperationDisposition"], "IdempotentReplay")
        self.assertEqual(len(duplicate["recovery"]["history"]), 1)

    def test_start_request_is_idempotent_across_runtime_restart(self) -> None:
        first = self.runtime.start(_request())
        restarted = ExecutionRuntime(ExecutionRuntimeRepository(JsonMapStore(self.root / "runtime.json")), platform=self.platform)
        replay = restarted.start(_request(sessionId="different-session-id"))

        self.assertEqual(replay["sessionId"], first["sessionId"])
        self.assertEqual(replay["lastOperationDisposition"], "IdempotentReplay")
        self.assertEqual(self.platform.events.list_recent(event_type="ExecutionStarted")["count"], 1)

    def test_retry_limit_is_enforced_without_provider_invocation(self) -> None:
        session = self.runtime.start(_request(maxRetries=1))
        self.runtime.timeout(session["sessionId"])
        retried = self.runtime.retry(session["sessionId"])
        self.runtime.report_failure(retried["sessionId"], {"type": "ProviderFailure", "reason": "Still unavailable."})

        with self.assertRaisesRegex(ValueError, "retry limit"):
            self.runtime.retry(session["sessionId"])
        self.assertFalse(self.runtime.diagnostics(session["sessionId"])["providerInvoked"])

    def test_cancel_is_idempotent_and_resumable(self) -> None:
        session = self.runtime.start(_request())
        cancelled = self.runtime.cancel(session["sessionId"], "Developer paused work.")
        replay = self.runtime.cancel(session["sessionId"], "Duplicate cancel callback.")
        resumed = self.runtime.resume(session["sessionId"], "Developer continued work.")

        self.assertEqual(cancelled["status"], "Cancelled")
        self.assertEqual(replay["lastOperationDisposition"], "IdempotentReplay")
        self.assertEqual(resumed["status"], "AwaitingResponse")

    def test_recovery_api_exposes_commands(self) -> None:
        router = build_runtime_recovery_router(self.runtime)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {
            ("POST", "/execution-runtime/{session_id}/retry"),
            ("POST", "/execution-runtime/{session_id}/resume"),
            ("POST", "/execution-runtime/{session_id}/timeout"),
            ("POST", "/execution-runtime/{session_id}/failure"),
        })
        session = self.runtime.start(_request())
        timed_out = routes[("POST", "/execution-runtime/{session_id}/timeout")](
            session["sessionId"], {"reason": "API timeout"}
        )
        retried = routes[("POST", "/execution-runtime/{session_id}/retry")](
            session["sessionId"], {"reason": "API retry"}
        )
        self.assertEqual(timed_out["status"], "TimedOut")
        self.assertEqual(retried["status"], "AwaitingResponse")

    def test_retry_reopens_observability_timeline_and_preserves_attempt_history(self) -> None:
        observability = RuntimeObservabilityService(
            RuntimeTraceRepository(JsonMapStore(self.root / "traces.json")),
            self.repository,
        )
        self.platform.event_handlers.subscribe("*", observability)
        session = self.runtime.start(_request(correlationId="corr-recovery-trace", idempotencyKey="trace-start"))
        self.runtime.timeout(session["sessionId"], "Provider timeout")
        failed_trace = observability.get("corr-recovery-trace")

        self.runtime.retry(session["sessionId"], "Retry provider callback")
        running_trace = observability.get("corr-recovery-trace")
        self.runtime.receive_response(session["sessionId"], _response(), {"responseId": "trace-final"})
        recovered_trace = observability.get("corr-recovery-trace")

        self.assertEqual(failed_trace["status"], "TimedOut")
        self.assertEqual(running_trace["status"], "Running")
        self.assertEqual(running_trace["currentStage"], "Execution Started")
        self.assertEqual(len(running_trace["attemptHistory"]), 1)
        self.assertEqual(recovered_trace["status"], "Completed")
        self.assertEqual(recovered_trace["timeline"][-1]["status"], "Recovered")


if __name__ == "__main__":
    unittest.main()
