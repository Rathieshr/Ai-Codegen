"""Phase 6.10 Azure DevOps operational validation."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .architecture import AzureDevOpsArchitectureVerifier
from .safety import LiveTestSafetyPolicy
from .store import AzureDevOpsHardeningStore


OPERATIONAL_VERSION = "6.10"
FLOWS = (
    ("planning-pack-hierarchy", "Manual requirement to approved hierarchy"),
    ("approved-work-item-update", "Existing work item approved update"),
    ("approved-estimate-update", "Story estimate and dependency update"),
    ("approved-pr-comment", "PR analysis and approved comment"),
    ("stale-recommendation-block", "Changed work item blocks stale recommendation"),
    ("duplicate-webhook-once", "Duplicate webhook is processed once"),
    ("permission-loss-safe-failure", "Permission loss fails safely"),
    ("scheduled-reconciliation", "Reconciliation repairs missed event state"),
    ("real-sprint-report", "Sprint burndown, blockers, and forecast"),
)


class AzureDevOpsOperationalValidator:
    def __init__(self, storage_root: Path, *, executor: Any, architecture: AzureDevOpsArchitectureVerifier, safety: LiveTestSafetyPolicy | None = None, platform: Any | None = None) -> None:
        self.executor = executor
        self.architecture = architecture
        self.safety = safety or LiveTestSafetyPolicy.from_environment()
        self.platform = platform
        self.store = AzureDevOpsHardeningStore(storage_root)

    def run(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = dict(request or {})
        environment = self.safety.validate(request, executor_is_mock=bool(getattr(self.executor, "is_mock", False)))
        correlation_id = str(request.get("correlationId") or f"corr-ado-operational-{uuid4().hex[:12]}")
        run_id = f"ado-operational-{uuid4().hex[:12]}"
        results, trace, stages = [], [], []
        for sequence, (flow_id, name) in enumerate(FLOWS, start=1):
            started = time.perf_counter()
            try:
                outcome = self.executor.execute(flow_id, request, correlation_id)
                passed, error = bool(outcome.get("passed")), ""
            except Exception as exc:
                outcome, passed, error = {"details": str(exc), "evidence": {}, "stages": []}, False, type(exc).__name__
            flow_stages = [str(item) for item in outcome.get("stages") or []]
            stages.extend(flow_stages)
            for stage in flow_stages:
                trace.append({"sequence": len(trace) + 1, "flowId": flow_id, "stage": stage, "correlationId": correlation_id})
            result = {
                "flowId": flow_id, "name": name, "status": "Passed" if passed else "Failed", "passed": passed,
                "durationMs": round((time.perf_counter() - started) * 1000, 2), "correlationId": correlation_id,
                "details": str(outcome.get("details") or ""), "errorType": error,
                "evidence": outcome.get("evidence") if isinstance(outcome.get("evidence"), dict) else {},
            }
            results.append(result)
            self._record(result, run_id, environment["projectId"], correlation_id)
        architecture = self.architecture.verify(self.executor.sdk, stages)
        gates = self._gates(results, architecture, environment)
        blockers = [gate["details"] for gate in gates if not gate["passed"]]
        live_evidence = environment["mode"] == "Live" and environment["writesAllowed"] and not bool(getattr(self.executor, "is_mock", False))
        if not live_evidence:
            blockers.append("A successful live run with approved writes against the allow-listed ADO test project is required before UI work.")
        report = {
            "runId": run_id, "operationalVersion": OPERATIONAL_VERSION, "generatedAt": _now(),
            "mode": environment["mode"], "projectId": environment["projectId"], "writesAllowed": environment["writesAllowed"],
            "correlationId": correlation_id, "flows": results, "trace": trace, "architecture": architecture,
            "qualityGates": gates,
            "readiness": {"status": "UI Ready" if not blockers else "Blocked", "liveEvidence": live_evidence, "blockers": blockers},
        }
        return self.store.save(report)

    def latest(self) -> dict[str, Any] | None:
        return self.store.latest()

    def trace(self, correlation_id: str) -> dict[str, Any] | None:
        report = next((item for item in self.store.list(200) if item.get("correlationId") == correlation_id), None)
        return {"correlationId": correlation_id, "trace": report.get("trace") or [], "runId": report.get("runId")} if report else None

    def readiness(self) -> dict[str, Any]:
        report = self.latest()
        if not report:
            return {"status": "NotValidated", "operationalVersion": OPERATIONAL_VERSION, "blockers": ["Run Phase 6.10 against the isolated ADO test project."]}
        return {"runId": report["runId"], "generatedAt": report["generatedAt"], **report["readiness"]}

    @staticmethod
    def _gates(results: list[dict[str, Any]], architecture: dict[str, Any], environment: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = {item["flowId"]: item.get("evidence") or {} for item in results}
        writes = [evidence.get(key, {}) for key in ("planning-pack-hierarchy", "approved-work-item-update", "approved-estimate-update", "approved-pr-comment")]
        write_controls = all(all(item.get(key) for key in ("preview", "approved", "idempotent", "revisionProtected", "audited")) for item in writes)
        pr = evidence.get("approved-pr-comment", {})
        sprint = evidence.get("real-sprint-report", {})
        failure = evidence.get("permission-loss-safe-failure", {})
        reconciliation = evidence.get("scheduled-reconciliation", {})
        production_safe = environment["projectId"].lower() not in {"production", "prod"}
        return [
            _gate("all_operational_flows", len(results) == len(FLOWS) and all(item["passed"] for item in results), "All nine operational flows must pass."),
            _gate("architecture_boundary", architecture.get("passed") is True, "ADO access must follow adapter, platform event/job, SDK, intelligence, approval, automation, audit."),
            _gate("read_write_separation", bool(evidence.get("permission-loss-safe-failure", {}).get("readWriteSeparated") and evidence.get("permission-loss-safe-failure", {}).get("audited")), "Read and write permissions must be separated and denied writes must be audited."),
            _gate("write_controls", write_controls, "Every write must have preview, approval, idempotency, revision protection, and audit evidence."),
            _gate("pr_grounding", bool(pr.get("executionPackage") and pr.get("actualDiff")), "PR analysis must be grounded in the Execution Package and actual changed files."),
            _gate("real_sprint_data", bool(sprint.get("adoWorkItems") and sprint.get("burndown") and sprint.get("forecast")), "Sprint metrics must use synchronized ADO work items."),
            _gate("failure_retry_visibility", bool(failure.get("apiVisible") and reconciliation.get("apiVisible")), "Failure and retry/reconciliation states must be visible through APIs."),
            _gate("non_production_target", production_safe, "Operational validation must never target production."),
            _gate("phase6_contract_stability", bool(evidence.get("planning-pack-hierarchy", {}).get("stableApi") and architecture.get("passed")), "Phase 6 APIs and architecture contracts must remain stable and documented."),
        ]

    def _record(self, result: dict[str, Any], run_id: str, project_id: str, correlation_id: str) -> None:
        if not self.platform:
            return
        self.platform.activity.add_activity({"activityType": "AzureDevOpsOperationalFlow", "title": result["name"], "description": result["details"], "source": "API", "projectId": project_id, "correlationId": correlation_id, "metadata": {"runId": run_id, "status": result["status"]}})
        self.platform.audit.record({"action": "AzureDevOpsOperationalFlowCompleted", "actor": "system", "source": "API", "targetType": "AzureDevOpsOperationalValidation", "targetId": run_id, "after": {"flowId": result["flowId"], "status": result["status"]}, "correlationId": correlation_id})


def _gate(gate_id: str, passed: bool, details: str) -> dict[str, Any]:
    return {"gateId": gate_id, "passed": bool(passed), "status": "Passed" if passed else "Failed", "details": details}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
