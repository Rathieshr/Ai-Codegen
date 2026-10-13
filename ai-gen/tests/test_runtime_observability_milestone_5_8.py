from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.execution_runtime import (
    ExecutionRuntime,
    ExecutionRuntimeRepository,
    RuntimeObservabilityService,
    RuntimeTraceRepository,
    build_runtime_observability_router,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


def _request(index: int = 1) -> dict:
    return {
        "executionPromptId": f"prompt-{index}",
        "executionPlanVersion": f"plan-{index}",
        "executionPackageVersion": f"package-{index}",
        "repositorySnapshotVersion": f"snapshot-{index}",
        "provider": "Azure OpenAI",
        "model": "GPT-5",
        "correlationId": f"corr-observe-{index}",
        "runtimeContext": {"repositoryId": "repo-gridhub"},
    }


def _response() -> dict:
    content = {
        "summary": "Updated device health behavior.",
        "artifacts": [{"type": "Code", "path": "src/DeviceHealth.cs", "changeType": "Modified"}],
    }
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 300, "completion_tokens": 120, "total_tokens": 420},
    }


class RuntimeObservabilityMilestone58Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.runtime_repository = ExecutionRuntimeRepository(JsonMapStore(self.root / "runtime.json"))
        self.observability = RuntimeObservabilityService(
            RuntimeTraceRepository(JsonMapStore(self.root / "traces.json")),
            self.runtime_repository,
        )
        self.platform.event_handlers.subscribe("*", self.observability)
        self.runtime = ExecutionRuntime(self.runtime_repository, platform=self.platform)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_complete_execution_has_canonical_timeline_and_metrics(self) -> None:
        session = self.runtime.start(_request())
        self._publish("PromptGenerated", session, {"compiledPromptId": "compiled-1"})
        self._publish("ProviderCalled", session, {"provider": "Azure OpenAI", "model": "GPT-5"})
        self.runtime.receive_response(session["sessionId"], _response(), {"durationMs": 730})
        self._publish("EngineeringDiffCompleted", session, {"engineeringDiffId": "diff-1", "changeCount": 1})
        self._publish("ValidationCompleted", session, {"decisionId": "validation-1", "confidence": 0.93})
        self._publish("QACompleted", session, {"qaExecutionPlanId": "qa-1"})
        self._publish("MemoryCandidateCreated", session, {"candidateId": "memory-1"})

        trace = self.observability.get(session["correlationId"])

        self.assertEqual(
            [item["stage"] for item in trace["timeline"]],
            [
                "Execution Started", "Prompt Generated", "Provider Called", "Response Received",
                "Interpreted", "Engineering Diff", "Validation", "QA", "Memory", "Completed",
            ],
        )
        self.assertEqual(trace["status"], "Completed")
        self.assertEqual(trace["metrics"]["provider"], "Azure OpenAI")
        self.assertEqual(trace["metrics"]["model"], "GPT-5")
        self.assertEqual(trace["metrics"]["tokens"], {"input": 300, "output": 120, "total": 420})
        self.assertEqual(trace["metrics"]["confidence"], self.runtime.get(session["sessionId"])["confidence"])
        self.assertEqual(trace["correlationId"], "corr-observe-1")

    def test_multiple_executions_are_isolated(self) -> None:
        first = self.runtime.start(_request(1))
        second = self.runtime.start(_request(2))
        self.runtime.receive_response(first["sessionId"], _response())
        self.runtime.receive_response(second["sessionId"], _response())

        result = self.observability.list()

        self.assertEqual(result["count"], 2)
        self.assertEqual({item["sessionId"] for item in result["traces"]}, {first["sessionId"], second["sessionId"]})
        self.assertEqual({item["correlationId"] for item in result["traces"]}, {"corr-observe-1", "corr-observe-2"})

    def test_concurrent_sessions_do_not_overwrite_each_other(self) -> None:
        def record(index: int) -> None:
            correlation = f"corr-concurrent-{index}"
            session = f"session-concurrent-{index}"
            self.observability.record(self._event("ExecutionStarted", correlation, session, index * 2))
            self.observability.record(self._event("ExecutionCompleted", correlation, session, index * 2 + 1))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(record, range(24)))

        result = self.observability.list(limit=100)
        self.assertEqual(result["count"], 24)
        self.assertEqual(len({item["traceId"] for item in result["traces"]}), 24)
        self.assertTrue(all(item["status"] == "Completed" for item in result["traces"]))

    def test_long_running_execution_reports_live_duration(self) -> None:
        started = datetime.now(timezone.utc) - timedelta(minutes=7)
        self.observability.record({
            "eventId": "event-long-running",
            "eventType": "ExecutionStarted",
            "correlationId": "corr-long-running",
            "createdAt": started.isoformat(),
            "payload": {"sessionId": "session-long-running", "provider": "Claude", "model": "Claude Code"},
        })

        trace = self.observability.get("corr-long-running")

        self.assertEqual(trace["status"], "Running")
        self.assertEqual(trace["currentStage"], "Execution Started")
        self.assertGreaterEqual(trace["durationMs"], 7 * 60 * 1000)
        self.assertEqual(trace["metrics"]["durationMs"], trace["durationMs"])

    def test_warning_and_failure_metrics_are_aggregated(self) -> None:
        self.observability.record({
            "eventId": "event-failed",
            "eventType": "ExecutionFailed",
            "correlationId": "corr-failed",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "payload": {"sessionId": "session-failed", "reason": "Provider timeout", "warnings": ["Retry exhausted"]},
        })
        trace = self.observability.get("corr-failed")
        self.assertEqual(trace["status"], "Failed")
        self.assertEqual(trace["metrics"]["warnings"], ["Retry exhausted"])
        self.assertEqual(trace["metrics"]["failures"][0]["reason"], "Provider timeout")

    def test_duplicate_event_is_idempotent(self) -> None:
        event = self._event("ExecutionStarted", "corr-idempotent", "session-idempotent", 1)
        self.observability.record(event)
        self.observability.record(event)
        trace = self.observability.get("corr-idempotent")
        self.assertEqual(len(trace["timeline"]), 1)
        self.assertEqual(len(trace["timeline"][0]["events"]), 1)

    def test_api_exposes_list_and_detail_without_mutating_runtime(self) -> None:
        session = self.runtime.start(_request())
        router = build_runtime_observability_router(self.observability)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}

        self.assertEqual(set(routes), {("GET", "/runtime/traces"), ("GET", "/runtime/traces/{trace_id}")})
        before = self.runtime.get(session["sessionId"])
        listing = routes[("GET", "/runtime/traces")]("", "", 100)
        detail = routes[("GET", "/runtime/traces/{trace_id}")](listing["traces"][0]["traceId"])
        after = self.runtime.get(session["sessionId"])

        self.assertEqual(listing["count"], 1)
        self.assertEqual(detail["sessionId"], session["sessionId"])
        self.assertEqual(before, after)

    def _publish(self, event_type: str, session: dict, payload: dict) -> None:
        self.platform.events.publish({
            "eventType": event_type,
            "source": "Test",
            "correlationId": session["correlationId"],
            "payload": {"sessionId": session["sessionId"], **payload},
        })

    @staticmethod
    def _event(event_type: str, correlation: str, session: str, index: int) -> dict:
        return {
            "eventId": f"event-{index}",
            "eventType": event_type,
            "correlationId": correlation,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "payload": {"sessionId": session},
        }


if __name__ == "__main__":
    unittest.main()
