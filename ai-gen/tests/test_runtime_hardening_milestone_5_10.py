from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.execution_runtime import (
    RuntimeHardeningHarness,
    build_runtime_hardening_router,
    render_runtime_benchmark_markdown,
)


class RuntimeHardeningMilestone510Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.harness = RuntimeHardeningHarness(Path(cls.temp.name))
        cls.report = cls.harness.run()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_repository_prompt_and_response_pressure_complete(self) -> None:
        workloads = {value["id"]: value for value in self.report["workloads"]}
        self.assertEqual(set(workloads), {
            "small-repository", "large-repository", "small-prompt", "large-prompt", "large-response"
        })
        self.assertTrue(all(value["status"] == "Passed" for value in workloads.values()))
        self.assertGreater(workloads["large-repository"]["repositoryFiles"], workloads["small-repository"]["repositoryFiles"])
        self.assertGreater(workloads["large-prompt"]["promptBytes"], workloads["small-prompt"]["promptBytes"])
        self.assertEqual(workloads["large-response"]["artifactCount"], 600)
        self.assertGreater(workloads["large-response"]["responseBytes"], 600000)
        self.assertEqual(workloads["large-response"]["tokenUsage"]["total_tokens"], 128000)

    def test_concurrent_execution_has_no_failures(self) -> None:
        result = self.report["concurrency"]
        self.assertEqual(result["sessions"], 24)
        self.assertEqual(result["completed"], 24)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["failureRate"], 0.0)
        self.assertGreaterEqual(result["p95QueueTimeMs"], 0)

    def test_recovery_survives_timeout_duplicate_partial_and_restart(self) -> None:
        recovery = self.report["recovery"]
        self.assertEqual(recovery["status"], "Passed")
        for field in ("timeoutRecovered", "duplicateIgnored", "partialPersisted", "restartResumed", "attemptHistoryPreserved"):
            self.assertTrue(recovery[field], field)

    def test_performance_metrics_capture_required_signals(self) -> None:
        performance = self.report["performance"]
        for field in ("averageLatencyMs", "p95LatencyMs", "maximumLatencyMs", "cpuTimeMs", "peakMemoryMb", "maximumResponseBytes", "queueTimeMs"):
            self.assertGreater(performance[field], 0, field)
        self.assertEqual(performance["failureRate"], 0.0)
        self.assertEqual(performance["status"], "Passed")

    def test_runtime_api_regression_is_complete(self) -> None:
        regression = self.report["regression"]
        self.assertEqual(regression["status"], "Passed")
        self.assertEqual(regression["expectedRoutes"], 12)
        self.assertEqual(regression["actualRoutes"], 12)
        self.assertEqual(regression["missingRoutes"], [])
        self.assertEqual(regression["unexpectedRoutes"], [])
        self.assertTrue(regression["idempotentStart"])

    def test_harness_never_uses_external_write_authority(self) -> None:
        environment = self.report["environment"]
        self.assertFalse(environment["providerInvoked"])
        for field in ("networkCalls", "repositoryWrites", "gitOperations", "azureDevOpsWrites"):
            self.assertEqual(environment[field], 0, field)

    def test_all_quality_gates_pass_and_report_is_persisted(self) -> None:
        self.assertEqual(self.report["readiness"]["status"], "Production Ready")
        self.assertEqual(self.report["readiness"]["passedGates"], self.report["readiness"]["totalGates"])
        self.assertTrue(all(gate["passed"] for gate in self.report["qualityGates"]))
        self.assertEqual(self.harness.get(self.report["runId"])["runId"], self.report["runId"])
        self.assertEqual(self.harness.latest()["runId"], self.report["runId"])

    def test_hardening_api_and_markdown_report_are_available(self) -> None:
        router = build_runtime_hardening_router(self.harness)
        routes = {(next(iter(route.methods)), route.path) for route in router.routes}
        self.assertEqual(routes, {
            ("POST", "/runtime/hardening/run"),
            ("GET", "/runtime/hardening/report"),
            ("GET", "/runtime/hardening/runs/{run_id}"),
        })
        markdown = render_runtime_benchmark_markdown(self.report)
        self.assertIn("# Execution Runtime Benchmark", markdown)
        self.assertIn("Production Ready", markdown)
        self.assertIn("Large AI Response", markdown)
        self.assertIn("Known Limitations", markdown)


if __name__ == "__main__":
    unittest.main()
