"""Event-driven observability for every HEI AI execution."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from .repository import RuntimeTraceRepository


STAGE_ORDER = (
    "Execution Started",
    "Prompt Generated",
    "Provider Called",
    "Response Received",
    "Interpreted",
    "Engineering Diff",
    "Validation",
    "QA",
    "Memory",
    "Completed",
)

EVENT_STAGES = {
    "ExecutionStarted": "Execution Started",
    "ExecutionResumed": "Execution Started",
    "ExecutionRetried": "Execution Started",
    "PromptCompilationCompleted": "Prompt Generated",
    "CompiledPromptReused": "Prompt Generated",
    "TokenOptimizationCompleted": "Prompt Generated",
    "BudgetedPromptReused": "Prompt Generated",
    "PromptGenerated": "Prompt Generated",
    "ProviderCalled": "Provider Called",
    "ExecutionResponseReceived": "Response Received",
    "ExecutionPartialResponseReceived": "Response Received",
    "ResponseReceived": "Response Received",
    "ExecutionInterpreted": "Interpreted",
    "ResponseInterpreted": "Interpreted",
    "ArtifactsExtracted": "Interpreted",
    "EngineeringDiffCompleted": "Engineering Diff",
    "EngineeringDiffFailed": "Engineering Diff",
    "ValidationRequested": "Validation",
    "ValidationCompleted": "Validation",
    "ValidationSkipped": "Validation",
    "ValidationBlocked": "Validation",
    "QARequested": "QA",
    "QACompleted": "QA",
    "QASkipped": "QA",
    "MemoryCandidateCreated": "Memory",
    "MemoryCandidateRejected": "Memory",
    "MemoryCaptureRequested": "Memory",
    "MemoryCaptureApproved": "Memory",
    "ExecutionCompleted": "Completed",
    "ExecutionFailed": "Completed",
    "ExecutionCancelled": "Completed",
    "ExecutionTimedOut": "Completed",
    "ExecutionRecovered": "Completed",
}

FAILURE_EVENTS = {
    "ExecutionFailed",
    "ExecutionTimedOut",
    "ResponseInterpretationFailed",
    "EngineeringDiffFailed",
    "ValidationBlocked",
}


class RuntimeObservabilityService:
    """Builds safe trace projections by observing existing platform events."""

    def __init__(self, repository: RuntimeTraceRepository, runtime_repository: Any | None = None) -> None:
        self.repository = repository
        self.runtime_repository = runtime_repository
        self._lock = RLock()

    def handle(self, event: dict[str, Any]) -> None:
        try:
            self.record(event)
        except Exception:
            # Observability must never interrupt the engineering workflow it observes.
            return

    def record(self, event: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        event_type = str(event.get("eventType") or event.get("type") or "")
        stage = EVENT_STAGES.get(event_type)
        if not stage:
            return None
        correlation_id = str(event.get("correlationId") or "").strip()
        if not correlation_id:
            return None
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        session_id = str(payload.get("sessionId") or event.get("sessionId") or "")
        with self._lock:
            trace_id = _trace_id(correlation_id)
            trace = self.repository.get(trace_id) or _new_trace(trace_id, correlation_id)
            if _event_seen(trace, str(event.get("eventId") or "")):
                return self._project(trace)
            if event_type in {"ExecutionRetried", "ExecutionResumed"}:
                _reopen_trace(trace, event_type, event)
            session = self._session(session_id)
            _merge_identity(trace, session_id, event, payload, session)
            _merge_stage(trace, stage, event_type, event, payload)
            _merge_metrics(trace, event_type, payload, session)
            trace["updatedAt"] = str(event.get("createdAt") or _now())
            _update_state(trace, event_type)
            saved = self.repository.save(trace)
            return self._project(saved)

    def list(self, *, status: str = "", provider: str = "", limit: int = 100) -> dict[str, Any]:
        with self._lock:
            traces = [self._project(value) for value in self.repository.list()]
        if status:
            traces = [value for value in traces if str(value.get("status") or "").casefold() == status.casefold()]
        if provider:
            traces = [value for value in traces if str((value.get("metrics") or {}).get("provider") or "").casefold() == provider.casefold()]
        bounded = traces[:max(1, min(int(limit or 100), 500))]
        return {"traces": bounded, "count": len(traces)}

    def get(self, trace_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.repository.get(trace_id)
            return self._project(value) if value else None

    def _project(self, trace: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(trace)
        value["durationMs"] = _duration_ms(value)
        value["metrics"]["durationMs"] = value["durationMs"]
        value["timeline"] = sorted(
            value.get("timeline") or [],
            key=lambda item: STAGE_ORDER.index(item["stage"]),
        )
        value["currentStage"] = _current_stage(value)
        return value

    def _session(self, session_id: str) -> dict[str, Any]:
        if not session_id or not self.runtime_repository:
            return {}
        value = self.runtime_repository.get(session_id)
        return value if isinstance(value, dict) else {}


def _new_trace(trace_id: str, correlation_id: str) -> dict[str, Any]:
    return {
        "traceId": trace_id,
        "runtimeObservabilityVersion": "5.8",
        "sessionId": "",
        "correlationId": correlation_id,
        "status": "Running",
        "currentStage": "",
        "startedAt": "",
        "completedAt": "",
        "updatedAt": "",
        "durationMs": 0.0,
        "timeline": [],
        "metrics": {
            "durationMs": 0.0,
            "provider": "",
            "model": "",
            "tokens": {"input": 0, "output": 0, "total": 0},
            "confidence": 0.0,
            "warnings": [],
            "failures": [],
            "correlationId": correlation_id,
        },
        "sourceVersions": {},
    }


def _merge_identity(trace: dict[str, Any], session_id: str, event: dict, payload: dict, session: dict) -> None:
    trace["sessionId"] = session_id or str(session.get("sessionId") or trace.get("sessionId") or "")
    trace["repositoryId"] = str(event.get("repositoryId") or trace.get("repositoryId") or "")
    versions = trace.setdefault("sourceVersions", {})
    for target, key in (
        ("executionPlan", "executionPlanVersion"),
        ("executionPackage", "executionPackageVersion"),
        ("repositorySnapshot", "repositorySnapshotVersion"),
    ):
        value = session.get(key) or payload.get(key)
        if value:
            versions[target] = str(value)


def _merge_stage(trace: dict[str, Any], stage: str, event_type: str, event: dict, payload: dict) -> None:
    timeline = trace.setdefault("timeline", [])
    item = next((value for value in timeline if value.get("stage") == stage), None)
    at = str(event.get("createdAt") or _now())
    status = _stage_status(event_type)
    event_record = {"eventId": str(event.get("eventId") or ""), "eventType": event_type, "at": at}
    if item is None:
        item = {
            "stage": stage,
            "status": status,
            "startedAt": at,
            "completedAt": at,
            "eventType": event_type,
            "events": [event_record],
            "details": _safe_details(payload),
        }
        timeline.append(item)
    else:
        item["status"] = status
        item["completedAt"] = at
        item["eventType"] = event_type
        item.setdefault("events", []).append(event_record)
        item["details"] = {**(item.get("details") or {}), **_safe_details(payload)}
    if stage == "Execution Started":
        trace["startedAt"] = trace.get("startedAt") or at
    if stage == "Completed":
        trace["completedAt"] = at


def _merge_metrics(trace: dict[str, Any], event_type: str, payload: dict, session: dict) -> None:
    metrics = trace["metrics"]
    result = session.get("result") if isinstance(session.get("result"), dict) else {}
    metrics["provider"] = str(payload.get("provider") or session.get("provider") or metrics.get("provider") or "")
    metrics["model"] = str(payload.get("model") or session.get("model") or metrics.get("model") or "")
    usage = payload.get("tokenUsage") if isinstance(payload.get("tokenUsage"), dict) else result.get("tokenUsage") if isinstance(result.get("tokenUsage"), dict) else {}
    if usage:
        metrics["tokens"] = _tokens(usage)
    confidence = payload.get("confidence", session.get("confidence"))
    if confidence is not None:
        try:
            metrics["confidence"] = round(float(confidence), 4)
        except (TypeError, ValueError):
            pass
    warnings = [*metrics.get("warnings", []), *_strings(payload.get("warnings")), *_strings(session.get("warnings"))]
    metrics["warnings"] = list(dict.fromkeys(warnings))
    if event_type in FAILURE_EVENTS:
        reason = str(payload.get("reason") or payload.get("error") or f"{event_type} was recorded.")
        failure = {"eventType": event_type, "reason": reason, "at": _now()}
        if failure not in metrics["failures"]:
            metrics["failures"].append(failure)


def _update_state(trace: dict[str, Any], event_type: str) -> None:
    if event_type in {"ExecutionRetried", "ExecutionResumed"}:
        trace["status"] = "Running"
    elif event_type == "ExecutionCompleted":
        trace["status"] = "Completed"
    elif event_type == "ExecutionRecovered":
        trace["status"] = "Completed"
    elif event_type == "ExecutionFailed":
        trace["status"] = "Failed"
    elif event_type == "ExecutionCancelled":
        trace["status"] = "Cancelled"
    elif event_type == "ExecutionTimedOut":
        trace["status"] = "TimedOut"
    elif trace.get("status") not in {"Completed", "Failed", "Cancelled"}:
        trace["status"] = "Running"


def _stage_status(event_type: str) -> str:
    if event_type in FAILURE_EVENTS:
        return "Failed"
    if event_type in {"ValidationSkipped", "QASkipped"}:
        return "Skipped"
    if event_type == "ExecutionCancelled":
        return "Cancelled"
    if event_type == "ExecutionRecovered":
        return "Recovered"
    if event_type == "MemoryCandidateRejected":
        return "Rejected"
    return "Completed"


def _reopen_trace(trace: dict[str, Any], event_type: str, event: dict[str, Any]) -> None:
    previous_timeline = deepcopy(trace.get("timeline") or [])
    if previous_timeline:
        trace.setdefault("attemptHistory", []).append({
            "status": trace.get("status"),
            "completedAt": trace.get("completedAt"),
            "timeline": previous_timeline,
            "recoveryEvent": event_type,
            "recordedAt": str(event.get("createdAt") or _now()),
        })
    trace["timeline"] = []
    trace["completedAt"] = ""


def _safe_details(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "sessionId", "status", "resultId", "artifactCount", "engineeringDiffId",
        "decisionId", "validationRequired", "qaExecutionPlanId", "qaRequired",
        "candidateId", "reason", "confidence", "changeCount", "impact",
    }
    return {key: deepcopy(value) for key, value in payload.items() if key in allowed}


def _event_seen(trace: dict[str, Any], event_id: str) -> bool:
    if not event_id:
        return False
    current = any(
        event.get("eventId") == event_id
        for stage in trace.get("timeline") or []
        for event in stage.get("events") or []
    )
    historical = any(
        event.get("eventId") == event_id
        for attempt in trace.get("attemptHistory") or []
        for stage in attempt.get("timeline") or []
        for event in stage.get("events") or []
    )
    return current or historical


def _tokens(usage: dict[str, Any]) -> dict[str, int]:
    input_tokens = _integer(usage.get("input") or usage.get("input_tokens") or usage.get("prompt_tokens"))
    output_tokens = _integer(usage.get("output") or usage.get("output_tokens") or usage.get("completion_tokens"))
    total = _integer(usage.get("total") or usage.get("total_tokens")) or input_tokens + output_tokens
    return {"input": input_tokens, "output": output_tokens, "total": total}


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value] if value else []
    return [str(item) for item in values if str(item).strip()]


def _duration_ms(trace: dict[str, Any]) -> float:
    started = _parse_time(str(trace.get("startedAt") or ""))
    if not started:
        return 0.0
    completed = _parse_time(str(trace.get("completedAt") or "")) or datetime.now(timezone.utc)
    return round(max(0.0, (completed - started).total_seconds() * 1000), 2)


def _current_stage(trace: dict[str, Any]) -> str:
    timeline = trace.get("timeline") or []
    if not timeline:
        return ""
    if trace.get("status") in {"Completed", "Failed", "Cancelled"}:
        return "Completed"
    return max(timeline, key=lambda item: STAGE_ORDER.index(item["stage"]))["stage"]


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _trace_id(correlation_id: str) -> str:
    digest = hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()[:16]
    return f"runtime_trace_{digest}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
