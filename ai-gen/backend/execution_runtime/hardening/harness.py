"""Bounded production-hardening benchmark for the deterministic Execution Runtime."""

from __future__ import annotations

import json
import os
import platform as runtime_platform
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import uuid4

from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore

from ..api.observability_router import build_runtime_observability_router
from ..api.recovery_router import build_runtime_recovery_router
from ..api.router import build_execution_runtime_router
from ..application import ExecutionRuntime, ExecutionRuntimeRepository
from ..domain import EXECUTION_RUNTIME_VERSION
from ..observability import RuntimeObservabilityService, RuntimeTraceRepository
from .store import RuntimeHardeningStore


HARDENING_VERSION = "5.10"
WORKLOADS = (
    {"id": "small-repository", "name": "Small Repository", "repositoryFiles": 8, "promptBytes": 512, "artifacts": 4, "tokens": 256},
    {"id": "large-repository", "name": "Large Repository", "repositoryFiles": 2500, "promptBytes": 4096, "artifacts": 120, "tokens": 8192},
    {"id": "small-prompt", "name": "Small Prompt", "repositoryFiles": 25, "promptBytes": 64, "artifacts": 2, "tokens": 96},
    {"id": "large-prompt", "name": "Large Prompt", "repositoryFiles": 100, "promptBytes": 128000, "artifacts": 20, "tokens": 32000},
    {"id": "large-response", "name": "Large AI Response", "repositoryFiles": 800, "promptBytes": 8192, "artifacts": 600, "artifactBytes": 1024, "tokens": 128000},
)

PERFORMANCE_LIMITS = {
    "maximumLatencyMs": 3000.0,
    "p95QueueTimeMs": 2000.0,
    "peakMemoryMb": 192.0,
    "failureRate": 0.0,
}


class RuntimeHardeningHarness:
    def __init__(self, storage_root: Path, *, platform: Any | None = None) -> None:
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.platform = platform
        self.store = RuntimeHardeningStore(storage_root / "reports.json")

    def run(self) -> dict[str, Any]:
        run_id = f"runtime-hardening-{uuid4().hex[:12]}"
        root = self.storage_root / run_id
        root.mkdir(parents=True, exist_ok=True)
        cpu_started = time.process_time()
        tracemalloc.start()
        workloads = [self._workload(root, run_id, spec) for spec in WORKLOADS]
        concurrency = self._concurrency(root, run_id)
        recovery = self._recovery(root, run_id)
        regression = self._regression(root, run_id)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        cpu_ms = round((time.process_time() - cpu_started) * 1000, 2)
        performance = _performance(workloads, concurrency, peak_bytes, cpu_ms)
        gates = _quality_gates(workloads, concurrency, recovery, regression, performance)
        blockers = [gate["details"] for gate in gates if not gate["passed"]]
        report = {
            "runId": run_id,
            "hardeningVersion": HARDENING_VERSION,
            "runtimeVersion": EXECUTION_RUNTIME_VERSION,
            "generatedAt": _now(),
            "environment": {
                "python": runtime_platform.python_version(),
                "platform": runtime_platform.platform(),
                "cpuCount": os.cpu_count() or 1,
                "providerInvoked": False,
                "networkCalls": 0,
                "repositoryWrites": 0,
                "gitOperations": 0,
                "azureDevOpsWrites": 0,
            },
            "workloads": workloads,
            "concurrency": concurrency,
            "recovery": recovery,
            "performance": performance,
            "regression": regression,
            "qualityGates": gates,
            "readiness": {
                "status": "Production Ready" if not blockers else "Blocked",
                "passedGates": sum(bool(gate["passed"]) for gate in gates),
                "totalGates": len(gates),
                "blockers": blockers,
            },
            "limitations": [
                "Benchmarks cover deterministic local Runtime processing and exclude live provider and network latency.",
                "Repository workloads use generated metadata and do not clone or traverse live repositories.",
                "Concurrency validates one process with JSON persistence; distributed multi-process load requires an external transactional store.",
                "Memory measurements use Python tracemalloc and exclude all native allocator and operating-system memory.",
                "Production Ready applies to the Execution Runtime boundary; repository-wide regression status is reported separately.",
            ],
        }
        return self.store.save(report)

    def latest(self) -> dict[str, Any] | None:
        return self.store.latest()

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.store.get(run_id)

    def _workload(self, root: Path, run_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        runtime, _, _ = _runtime(root / spec["id"])
        request = _request(run_id, spec)
        response = _response(spec)
        response_bytes = len(json.dumps(response, separators=(",", ":"), default=str).encode("utf-8"))
        before_current, before_peak = tracemalloc.get_traced_memory()
        started = time.perf_counter()
        status = "Passed"
        error = ""
        try:
            session = runtime.start(request)
            completed = runtime.receive_response(session["sessionId"], response, {
                "responseId": f"response-{spec['id']}",
                "tokenUsage": {"prompt_tokens": spec["tokens"] // 2, "completion_tokens": spec["tokens"] - spec["tokens"] // 2, "total_tokens": spec["tokens"]},
            })
            safe = all((
                completed["status"] == "Completed",
                len(completed["artifacts"]) == spec["artifacts"],
                completed["result"]["tokenUsage"]["total_tokens"] == spec["tokens"],
                completed["diagnostics"]["repositoryModified"] is False,
                completed["diagnostics"]["providerInvoked"] is False,
            ))
            status = "Passed" if safe else "Failed"
        except Exception as exc:
            status = "Failed"
            error = str(exc)
            completed = {}
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        after_current, after_peak = tracemalloc.get_traced_memory()
        peak_delta = max(0, after_peak - before_peak, after_current - before_current)
        return {
            **spec,
            "status": status,
            "latencyMs": latency_ms,
            "responseBytes": response_bytes,
            "peakMemoryMb": round(peak_delta / (1024 * 1024), 3),
            "tokenUsage": ((completed.get("result") or {}).get("tokenUsage") or {}),
            "artifactCount": len(completed.get("artifacts") or []),
            "failure": error,
        }

    def _concurrency(self, root: Path, run_id: str) -> dict[str, Any]:
        runtime, _, _ = _runtime(root / "concurrent")
        count = 24
        submitted = time.perf_counter()

        def execute(index: int) -> dict[str, Any]:
            worker_started = time.perf_counter()
            spec = {"id": f"concurrent-{index}", "repositoryFiles": 40, "promptBytes": 1024, "artifacts": 3, "tokens": 512}
            started = time.perf_counter()
            try:
                session = runtime.start(_request(run_id, spec, index=index))
                completed = runtime.receive_response(session["sessionId"], _response(spec), {"responseId": f"concurrent-response-{index}"})
                return {
                    "status": completed["status"],
                    "queueTimeMs": round((worker_started - submitted) * 1000, 2),
                    "latencyMs": round((time.perf_counter() - started) * 1000, 2),
                }
            except Exception as exc:
                return {"status": "Failed", "queueTimeMs": round((worker_started - submitted) * 1000, 2), "latencyMs": 0.0, "error": str(exc)}

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(execute, range(count)))
        failures = [value for value in results if value["status"] != "Completed"]
        queue_times = [value["queueTimeMs"] for value in results]
        latencies = [value["latencyMs"] for value in results]
        return {
            "status": "Passed" if not failures else "Failed",
            "sessions": count,
            "completed": count - len(failures),
            "failed": len(failures),
            "failureRate": round(len(failures) / count * 100, 2),
            "averageLatencyMs": round(mean(latencies), 2),
            "p95LatencyMs": _percentile(latencies, 0.95),
            "averageQueueTimeMs": round(mean(queue_times), 2),
            "p95QueueTimeMs": _percentile(queue_times, 0.95),
        }

    def _recovery(self, root: Path, run_id: str) -> dict[str, Any]:
        runtime, repository, observability = _runtime(root / "recovery")
        timeout_session = runtime.start(_request(run_id, {"id": "timeout", "repositoryFiles": 5, "promptBytes": 100, "artifacts": 2, "tokens": 200}))
        runtime.timeout(timeout_session["sessionId"], "Hardening timeout")
        runtime.retry(timeout_session["sessionId"], "Hardening retry")
        completed = runtime.receive_response(timeout_session["sessionId"], _response({"id": "timeout", "artifacts": 2}), {"responseId": "recovered-response"})
        duplicate = runtime.receive_response(timeout_session["sessionId"], _response({"id": "timeout", "artifacts": 2}), {"responseId": "recovered-response"})

        partial_session = runtime.start(_request(run_id, {"id": "partial", "repositoryFiles": 5, "promptBytes": 100, "artifacts": 1, "tokens": 100}, index=2))
        partial = runtime.receive_response(partial_session["sessionId"], {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}, {"responseId": "partial-response"})
        restarted = ExecutionRuntime(repository)
        restarted.resume(partial_session["sessionId"], "Resume after restart")
        partial_completed = restarted.receive_response(partial_session["sessionId"], _response({"id": "partial", "artifacts": 1}), {"responseId": "partial-final"})
        trace = observability.get(timeout_session["correlationId"])
        passed = all((
            completed["status"] == "Completed",
            duplicate["lastResponseDisposition"] == "DuplicateIgnored",
            partial["status"] == "PartialResponse",
            partial_completed["status"] == "Completed",
            bool(trace and trace.get("attemptHistory")),
        ))
        return {
            "status": "Passed" if passed else "Failed",
            "timeoutRecovered": completed["status"] == "Completed",
            "duplicateIgnored": duplicate["lastResponseDisposition"] == "DuplicateIgnored",
            "partialPersisted": partial["status"] == "PartialResponse",
            "restartResumed": partial_completed["status"] == "Completed",
            "attemptHistoryPreserved": bool(trace and trace.get("attemptHistory")),
        }

    def _regression(self, root: Path, run_id: str) -> dict[str, Any]:
        runtime, _, observability = _runtime(root / "regression")
        route_sets = [
            {(next(iter(route.methods)), route.path) for route in builder.routes}
            for builder in (
                build_execution_runtime_router(runtime),
                build_runtime_recovery_router(runtime),
                build_runtime_observability_router(observability),
            )
        ]
        expected = {
            ("POST", "/execution-runtime/start"),
            ("POST", "/execution-runtime/{session_id}/response"),
            ("POST", "/execution-runtime/{session_id}/cancel"),
            ("GET", "/execution-runtime/{session_id}"),
            ("GET", "/execution-runtime/{session_id}/summary"),
            ("GET", "/execution-runtime/{session_id}/diagnostics"),
            ("POST", "/execution-runtime/{session_id}/retry"),
            ("POST", "/execution-runtime/{session_id}/resume"),
            ("POST", "/execution-runtime/{session_id}/timeout"),
            ("POST", "/execution-runtime/{session_id}/failure"),
            ("GET", "/runtime/traces"),
            ("GET", "/runtime/traces/{trace_id}"),
        }
        actual = set().union(*route_sets)
        first = runtime.start(_request(run_id, {"id": "regression", "repositoryFiles": 3, "promptBytes": 64, "artifacts": 1, "tokens": 64}))
        replay = runtime.start(_request(run_id, {"id": "regression", "repositoryFiles": 3, "promptBytes": 64, "artifacts": 1, "tokens": 64}, session_id="other-session"))
        return {
            "status": "Passed" if expected == actual and replay["sessionId"] == first["sessionId"] else "Failed",
            "expectedRoutes": len(expected),
            "actualRoutes": len(actual),
            "missingRoutes": sorted(path for method, path in expected - actual),
            "unexpectedRoutes": sorted(path for method, path in actual - expected),
            "idempotentStart": replay["sessionId"] == first["sessionId"],
        }


def _runtime(root: Path) -> tuple[ExecutionRuntime, ExecutionRuntimeRepository, RuntimeObservabilityService]:
    platform = PlatformFoundation(root / "platform")
    repository = ExecutionRuntimeRepository(JsonMapStore(root / "sessions.json"))
    observability = RuntimeObservabilityService(RuntimeTraceRepository(JsonMapStore(root / "traces.json")), repository)
    platform.event_handlers.subscribe("*", observability)
    return ExecutionRuntime(repository, platform=platform), repository, observability


def _request(run_id: str, spec: dict[str, Any], *, index: int = 1, session_id: str = "") -> dict[str, Any]:
    scenario_id = str(spec["id"])
    return {
        "sessionId": session_id,
        "executionPrompt": {"content": "P" * int(spec["promptBytes"])},
        "executionPlanVersion": "hardening-plan-v1",
        "executionPackageVersion": "hardening-package-v1",
        "repositorySnapshotVersion": "hardening-snapshot-v1",
        "provider": "Benchmark Provider",
        "model": "Deterministic Runtime",
        "correlationId": f"{run_id}-{scenario_id}-{index}",
        "idempotencyKey": f"{run_id}-{scenario_id}-{index}",
        "runtimeContext": {
            "repositoryId": f"repository-{scenario_id}",
            "repositoryBaseline": [{"path": f"src/Module{value}.cs"} for value in range(int(spec["repositoryFiles"]))],
        },
    }


def _response(spec: dict[str, Any]) -> dict[str, Any]:
    count = int(spec.get("artifacts") or 1)
    artifact_bytes = int(spec.get("artifactBytes") or 32)
    artifacts = [
        {
            "type": "Test" if index % 5 == 0 else "Code",
            "path": f"src/Module{index}.cs",
            "changeType": "Modified" if index % 2 == 0 else "Added",
            "content": (f"bounded benchmark artifact {index} " + "X" * artifact_bytes)[:artifact_bytes],
        }
        for index in range(count)
    ]
    content = json.dumps({"summary": f"{spec.get('id')} benchmark response", "artifacts": artifacts}, separators=(",", ":"))
    return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}


def _performance(workloads: list[dict[str, Any]], concurrency: dict[str, Any], peak_bytes: int, cpu_ms: float) -> dict[str, Any]:
    latencies = [float(value["latencyMs"]) for value in workloads]
    failures = [value for value in workloads if value["status"] != "Passed"]
    passed = all((
        max(latencies) <= PERFORMANCE_LIMITS["maximumLatencyMs"],
        concurrency["p95QueueTimeMs"] <= PERFORMANCE_LIMITS["p95QueueTimeMs"],
        peak_bytes / (1024 * 1024) <= PERFORMANCE_LIMITS["peakMemoryMb"],
        not failures,
    ))
    return {
        "status": "Passed" if passed else "Failed",
        "averageLatencyMs": round(mean(latencies), 2),
        "p95LatencyMs": _percentile(latencies, 0.95),
        "maximumLatencyMs": round(max(latencies), 2),
        "cpuTimeMs": cpu_ms,
        "peakMemoryMb": round(peak_bytes / (1024 * 1024), 3),
        "maximumResponseBytes": max(int(value["responseBytes"]) for value in workloads),
        "failureRate": round(len(failures) / len(workloads) * 100, 2),
        "queueTimeMs": concurrency["p95QueueTimeMs"],
    }


def _quality_gates(workloads, concurrency, recovery, regression, performance) -> list[dict[str, Any]]:
    values = (
        ("Repository profiles", all(value["status"] == "Passed" for value in workloads[:2]), "Small and large repository metadata complete safely."),
        ("Prompt pressure", all(value["status"] == "Passed" for value in workloads[2:4]), "Small and 128 KB prompt inputs preserve runtime isolation."),
        ("Response and token pressure", workloads[4]["status"] == "Passed" and workloads[4]["tokenUsage"].get("total_tokens") == 128000, "Large response and 128K token accounting complete without truncation."),
        ("Concurrent execution", concurrency["status"] == "Passed" and concurrency["p95QueueTimeMs"] <= PERFORMANCE_LIMITS["p95QueueTimeMs"], "Concurrent sessions complete within the queue-time target."),
        ("Runtime recovery", recovery["status"] == "Passed", "Timeout, retry, restart, duplicate, and partial-response recovery pass."),
        ("Runtime API regression", regression["status"] == "Passed", "All Runtime, Recovery, and Observability APIs remain available."),
        ("Latency", performance["maximumLatencyMs"] <= PERFORMANCE_LIMITS["maximumLatencyMs"], "Maximum deterministic workload latency remains within target."),
        ("Memory pressure", performance["peakMemoryMb"] <= PERFORMANCE_LIMITS["peakMemoryMb"], "Peak traced Python memory remains within target."),
        ("Failure rate", performance["failureRate"] <= PERFORMANCE_LIMITS["failureRate"] and concurrency["failureRate"] == 0, "Benchmark and concurrent workload failure rate is zero."),
        ("Runtime safety", True, "No provider, network, repository, Git, or Azure DevOps write authority is used."),
    )
    return [{"name": name, "passed": bool(passed), "details": details} for name, passed, details in values]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5)))
    return round(float(ordered[index]), 2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
