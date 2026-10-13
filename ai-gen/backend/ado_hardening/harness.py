"""Phase 6 Azure DevOps end-to-end hardening harness."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .safety import LiveTestSafetyPolicy
from .store import AzureDevOpsHardeningStore


HARDENING_VERSION = "6.9"
SCENARIOS = (
    ("manual-requirement-hierarchy", "Manual requirement to approved hierarchy"),
    ("existing-epic-analysis", "Existing Epic quality and decomposition"),
    ("existing-story-estimation", "Existing Story tasks and estimation"),
    ("pull-request-approved-comment", "Pull request intelligence and approved comment"),
    ("stale-work-item-recommendation", "Work-item revision invalidates recommendation"),
    ("sprint-burndown-risk", "Sprint burndown and delivery risk"),
    ("build-failure-agent-response", "Build failure activity and agent response"),
    ("duplicate-webhook-idempotency", "Duplicate webhook idempotency"),
    ("permission-loss-safe-failure", "Permission loss safe failure"),
    ("azure-devops-outage-recovery", "Azure DevOps outage retry and recovery"),
)

DEFAULT_LIMITS_MS = {
    "initial_sync": 30000.0,
    "incremental_sync": 10000.0,
    "work_item_analysis": 15000.0,
    "hierarchy_creation_preview": 5000.0,
    "hierarchy_application": 30000.0,
    "pr_analysis": 20000.0,
    "sprint_report": 10000.0,
    "estimation": 10000.0,
    "agent_response": 5000.0,
}


class AzureDevOpsHardeningHarness:
    def __init__(self, storage_root: Path, *, executor, safety: LiveTestSafetyPolicy | None = None, platform=None) -> None:
        self.executor = executor
        self.safety = safety or LiveTestSafetyPolicy.from_environment()
        self.platform = platform
        self.store = AzureDevOpsHardeningStore(storage_root)

    def run(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = dict(request or {})
        environment = self.safety.validate(request, executor_is_mock=bool(getattr(self.executor, "is_mock", False)))
        run_id = f"ado-hardening-{uuid4().hex[:12]}"
        correlation_root = str(request.get("correlationId") or f"corr-{uuid4().hex[:12]}")
        results = []
        operation_timings: dict[str, list[float]] = {}
        for index, (scenario_id, name) in enumerate(SCENARIOS, start=1):
            started = time.perf_counter()
            correlation_id = f"{correlation_root}-{index:02d}"
            try:
                outcome = self.executor.execute(scenario_id, request, correlation_id)
                passed = bool(outcome.get("passed"))
                error = ""
            except Exception as exc:
                outcome = {"passed": False, "details": str(exc), "operations": [], "evidence": {}}
                passed = False
                error = type(exc).__name__
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            for operation in outcome.get("operations") or []:
                operation_timings.setdefault(str(operation), []).append(duration_ms)
            result = {
                "scenarioId": scenario_id,
                "name": name,
                "status": "Passed" if passed else "Failed",
                "passed": passed,
                "durationMs": duration_ms,
                "correlationId": correlation_id,
                "details": str(outcome.get("details") or ""),
                "errorType": error,
                "evidence": outcome.get("evidence") if isinstance(outcome.get("evidence"), dict) else {},
            }
            results.append(result)
            self._record(result, run_id, environment["projectId"])
        security = self._security(request)
        performance = self._performance(operation_timings, request)
        reliability = self._reliability(results)
        gates = self._gates(results, security, performance, reliability, environment)
        blockers = [item["details"] for item in gates if not item["passed"]]
        report = {
            "runId": run_id,
            "hardeningVersion": HARDENING_VERSION,
            "generatedAt": _now(),
            "mode": environment["mode"],
            "projectId": environment["projectId"],
            "writesAllowed": environment["writesAllowed"],
            "scenarios": results,
            "security": security,
            "reliability": reliability,
            "performance": performance,
            "qualityGates": gates,
            "readiness": {
                "status": "Command Center Ready" if not blockers else "Blocked",
                "passedGates": sum(1 for item in gates if item["passed"]),
                "totalGates": len(gates),
                "blockers": blockers,
            },
            "limitations": [
                "Mocked mode validates service contracts and failure behavior without measuring Azure DevOps network latency.",
                "Live mode requires an isolated allow-listed project and does not run unless explicitly enabled.",
                "Write scenarios remain preview-only unless both process and request write approvals are enabled.",
                "Performance baselines are environment-specific and should be compared by mode and test project.",
            ],
        }
        return self.store.save(report)

    def latest(self) -> dict[str, Any] | None:
        return self.store.latest()

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.store.get(run_id)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list(limit)

    def readiness(self) -> dict[str, Any]:
        report = self.latest()
        if not report:
            return {"status": "NotValidated", "hardeningVersion": HARDENING_VERSION, "blockers": ["Run Phase 6 hardening before enabling the Command Center UI."]}
        return {"runId": report["runId"], "generatedAt": report["generatedAt"], **report["readiness"]}

    def _security(self, request: dict[str, Any]) -> dict[str, Any]:
        probe = getattr(self.executor, "security_probe", None)
        if callable(probe):
            value = probe(request)
            if isinstance(value, dict):
                return value
        return {"passed": False, "checks": [{"checkId": "security_probe", "passed": False, "details": "The hardening executor did not provide security verification."}]}

    @staticmethod
    def _performance(operation_timings: dict[str, list[float]], request: dict[str, Any]) -> dict[str, Any]:
        configured = request.get("performanceLimitsMs") if isinstance(request.get("performanceLimitsMs"), dict) else {}
        baselines = []
        for operation, default_limit in DEFAULT_LIMITS_MS.items():
            values = operation_timings.get(operation) or []
            limit = float(configured.get(operation) or default_limit)
            duration = round(sum(values) / len(values), 2) if values else None
            baselines.append({
                "operation": operation,
                "sampleCount": len(values),
                "averageDurationMs": duration,
                "maximumDurationMs": max(values) if values else None,
                "limitMs": limit,
                "passed": bool(values) and max(values) <= limit,
            })
        measured = [item for item in baselines if item["sampleCount"]]
        return {"passed": len(measured) == len(DEFAULT_LIMITS_MS) and all(item["passed"] for item in measured), "baselines": baselines, "measuredOperations": len(measured)}

    @staticmethod
    def _reliability(results: list[dict[str, Any]]) -> dict[str, Any]:
        required = {
            "duplicate-webhook-idempotency": "idempotency",
            "permission-loss-safe-failure": "permissionFailure",
            "azure-devops-outage-recovery": "outageRecovery",
            "stale-work-item-recommendation": "staleRevision",
        }
        checks = []
        by_id = {item["scenarioId"]: item for item in results}
        for scenario_id, check_id in required.items():
            passed = bool((by_id.get(scenario_id) or {}).get("passed"))
            checks.append({"checkId": check_id, "passed": passed, "details": (by_id.get(scenario_id) or {}).get("details", "Scenario missing.")})
        return {"passed": all(item["passed"] for item in checks), "checks": checks}

    @staticmethod
    def _gates(results, security, performance, reliability, environment) -> list[dict[str, Any]]:
        all_scenarios = len(results) == len(SCENARIOS) and all(item["passed"] for item in results)
        by_id = {item["scenarioId"]: item for item in results}
        if not environment["writesAllowed"] or environment["mode"] == "Mocked":
            no_unapproved_writes = True
        else:
            hierarchy = (by_id.get("manual-requirement-hierarchy") or {}).get("evidence") or {}
            pull_request = (by_id.get("pull-request-approved-comment") or {}).get("evidence") or {}
            no_unapproved_writes = bool(
                hierarchy.get("preview")
                and (hierarchy.get("applied") or {}).get("status") == "Completed"
                and pull_request.get("preview")
                and (pull_request.get("posted") or {}).get("posted") is True
            )
        return [
            _gate("end_to_end_scenarios", all_scenarios, "All ten Phase 6 end-to-end scenarios must pass."),
            _gate("security", bool(security.get("passed")), "Credential, permission, route, audit, and project isolation checks must pass."),
            _gate("reliability", bool(reliability.get("passed")), "Idempotency, stale revision, permission loss, and outage recovery must pass."),
            _gate("performance", bool(performance.get("passed")), "Measured operations must remain within configured baselines."),
            _gate("write_safety", no_unapproved_writes, "Every write must be previewed, approved, revision-safe, idempotent, and auditable."),
        ]

    def _record(self, result: dict[str, Any], run_id: str, project_id: str) -> None:
        if not self.platform:
            return
        self.platform.activity.add_activity({"activityType": "AzureDevOpsHardeningScenario", "title": result["name"], "description": result["details"], "source": "API", "projectId": project_id, "correlationId": result["correlationId"], "metadata": {"runId": run_id, "status": result["status"]}})
        self.platform.audit.record({"action": "AzureDevOpsHardeningScenarioCompleted", "actor": "system", "source": "API", "targetType": "AzureDevOpsHardeningRun", "targetId": run_id, "after": {"scenarioId": result["scenarioId"], "status": result["status"]}, "correlationId": result["correlationId"]})


def _gate(gate_id: str, passed: bool, details: str) -> dict[str, Any]:
    return {"gateId": gate_id, "passed": bool(passed), "status": "Passed" if passed else "Failed", "details": details}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
