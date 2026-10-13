"""Deterministic orchestration of provider-response execution outcomes."""

from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from backend.token_intelligence.models import stable_hash

from ..comparison import RepositoryComparator
from ..diagnostics import build_diagnostics
from ..domain import EXECUTION_RUNTIME_VERSION, FAILURE_TYPES, RECOVERABLE_SESSION_STATUSES, TERMINAL_SESSION_STATUSES
from ..events import RuntimeEventPublisher
from ..interpreter import ResponseInterpreter
from ..memory import build_memory_candidate
from ..validation import build_downstream_intents
from .repository import ExecutionRuntimeRepository


class ExecutionRuntime:
    """Records and interprets AI outcomes without executing provider or repository work."""

    def __init__(
        self,
        repository: ExecutionRuntimeRepository,
        *,
        interpreter: ResponseInterpreter | None = None,
        comparator: RepositoryComparator | None = None,
        platform: Any | None = None,
    ) -> None:
        self.repository = repository
        self.interpreter = interpreter or ResponseInterpreter()
        self.comparator = comparator or RepositoryComparator()
        self.publisher = RuntimeEventPublisher(platform)
        self._lock = RLock()

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        _validate_start(request)
        idempotency_key = str(request.get("idempotencyKey") or "").strip()
        with self._lock:
            existing = self.repository.find_by_idempotency_key(idempotency_key)
            if existing:
                existing["lastOperationDisposition"] = "IdempotentReplay"
                return self.repository.save(existing)
        started_at = _now()
        session_id = str(request.get("sessionId") or f"execution_session_{uuid4().hex[:12]}")
        correlation_id = str(request.get("correlationId") or f"corr_{uuid4().hex[:12]}")
        runtime_context = request.get("runtimeContext") if isinstance(request.get("runtimeContext"), dict) else {}
        warnings: list[str] = []
        if not str(request.get("repositorySnapshotVersion") or ""):
            warnings.append("Repository snapshot version was not supplied; comparison confidence will be lower.")
        session: dict[str, Any] = {
            "sessionId": session_id,
            "runtimeVersion": EXECUTION_RUNTIME_VERSION,
            "idempotencyKey": idempotency_key,
            "executionPromptId": str(request.get("executionPromptId") or ""),
            "executionPlanVersion": str(request["executionPlanVersion"]),
            "executionPackageVersion": str(request["executionPackageVersion"]),
            "repositorySnapshotVersion": str(request.get("repositorySnapshotVersion") or ""),
            "provider": str(request["provider"]),
            "model": str(request["model"]),
            "startedAt": started_at,
            "completedAt": "",
            "status": "AwaitingResponse",
            "duration": 0.0,
            "correlationId": correlation_id,
            "developerId": str(request.get("developerId") or ""),
            "workspaceId": str(request.get("workspaceId") or ""),
            "branch": str(request.get("branch") or ""),
            "commitBefore": str(request.get("commitBefore") or ""),
            "commitAfter": "",
            "warnings": warnings,
            "confidence": 0.0,
            "runtimeContext": deepcopy(runtime_context),
            "result": None,
            "artifacts": [],
            "engineeringDiff": None,
            "downstreamIntents": [],
            "memoryCandidate": None,
            "prCandidate": None,
            "diagnostics": {},
            "attempt": 1,
            "maxRetries": max(0, min(int(request.get("maxRetries", 3)), 10)),
            "attemptStartedAt": started_at,
            "lastCheckpoint": "ExecutionStarted",
            "lastFailure": None,
            "responseHistory": [],
            "partialResponses": [],
            "duplicateResponseCount": 0,
            "lastResponseDisposition": "",
            "lastOperationDisposition": "Created",
            "recovery": {"retryCount": 0, "resumeCount": 0, "history": []},
        }
        session["diagnostics"] = build_diagnostics(session)
        with self._lock:
            existing_by_id = self.repository.get(session_id)
            if existing_by_id:
                if idempotency_key and existing_by_id.get("idempotencyKey") == idempotency_key:
                    return existing_by_id
                raise ValueError("Execution session already exists.")
            saved = self.repository.save(session)
        self.publisher.publish("ExecutionStarted", saved)
        self.publisher.activity(saved, "AI execution started", f"Execution session {session_id} is awaiting a provider response.")
        return saved

    def receive_response(
        self,
        session_id: str,
        provider_response: Any,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            return self._receive_response_locked(session_id, provider_response, metadata)

    def _receive_response_locked(
        self,
        session_id: str,
        provider_response: Any,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._required(session_id)
        metadata = metadata if isinstance(metadata, dict) else {}
        response_key = _response_key(provider_response, metadata)
        duplicate = next((item for item in session.get("responseHistory") or [] if item.get("responseKey") == response_key), None)
        if duplicate:
            session["duplicateResponseCount"] = int(session.get("duplicateResponseCount") or 0) + 1
            session["lastResponseDisposition"] = "DuplicateIgnored"
            session["lastOperationDisposition"] = "IdempotentReplay"
            session["diagnostics"] = build_diagnostics(session, session.get("result"), session.get("artifacts"), session.get("engineeringDiff"))
            saved = self.repository.save(session)
            self.publisher.publish("ExecutionDuplicateResponseIgnored", saved, {
                "responseKey": response_key,
                "originalDisposition": duplicate.get("disposition"),
            })
            return saved
        if session["status"] in TERMINAL_SESSION_STATUSES:
            raise ValueError(f"Execution session is already {session['status']}.")
        is_partial = _is_partial_response(provider_response, metadata)
        response_record = {
            "responseKey": response_key,
            "responseId": str(metadata.get("responseId") or ""),
            "receivedAt": _now(),
            "attempt": int(session.get("attempt") or 1),
            "partial": is_partial,
            "disposition": "Received",
        }
        session.setdefault("responseHistory", []).append(response_record)
        session["lastResponseDisposition"] = "Received"
        if is_partial:
            session["status"] = "PartialResponse"
            session["lastCheckpoint"] = "PartialResponse"
            response_record["disposition"] = "PartialStored"
            session.setdefault("partialResponses", []).append({
                **response_record,
                "providerResponse": deepcopy(provider_response),
            })
            session["diagnostics"] = build_diagnostics(session)
            saved = self.repository.save(session)
            self.publisher.publish("ExecutionResponseReceived", saved, {
                "responseKey": response_key,
                "partial": True,
            })
            self.publisher.publish("ExecutionPartialResponseReceived", saved, {
                "responseKey": response_key,
                "partialResponseCount": len(session["partialResponses"]),
            })
            return saved
        session["status"] = "Interpreting"
        session["lastCheckpoint"] = "ResponseReceived"
        self.repository.save(session)
        self.publisher.publish("ExecutionResponseReceived", session)
        operation_started = time.perf_counter()
        try:
            interpreted = self.interpreter.interpret(provider_response, session_id=session_id)
            session["commitAfter"] = str(metadata.get("commitAfter") or "")
            artifacts = interpreted["artifacts"]
            engineering_diff = self.comparator.compare(session, artifacts)
            result = _result(session, interpreted, provider_response, metadata, operation_started)
            session.update({
                "result": result,
                "artifacts": artifacts,
                "engineeringDiff": engineering_diff,
                "warnings": list(dict.fromkeys([*session["warnings"], *result["warnings"]])),
                "confidence": result["confidence"],
            })
            response_record["disposition"] = "Processed"
            session["lastResponseDisposition"] = "Processed"
            self.publisher.publish("ExecutionInterpreted", session, {
                "resultId": result["resultId"],
                "artifactCount": len(artifacts),
                "engineeringDiffId": engineering_diff["diffId"],
            })
            intents = build_downstream_intents(session, result, engineering_diff)
            session["downstreamIntents"] = intents
            session["memoryCandidate"] = build_memory_candidate(session, result, artifacts, engineering_diff)
            session["prCandidate"] = _pr_candidate(session, result, engineering_diff)
            session["status"] = "Completed"
            session["lastCheckpoint"] = "Completed"
            session["completedAt"] = _now()
            session["duration"] = _elapsed_ms(session["startedAt"])
            session["diagnostics"] = build_diagnostics(session, result, artifacts, engineering_diff)
            saved = self.repository.save(session)
            self.publisher.publish("ExecutionCompleted", saved, {
                "resultId": result["resultId"],
                "artifactCount": len(artifacts),
                "engineeringDiffId": engineering_diff["diffId"],
                "downstreamIntentCount": len(intents),
            })
            recovery = saved.get("recovery") or {}
            if int(recovery.get("retryCount") or 0) or int(recovery.get("resumeCount") or 0):
                self.publisher.publish("ExecutionRecovered", saved, {
                    "attempt": saved.get("attempt"),
                    "retryCount": recovery.get("retryCount"),
                    "resumeCount": recovery.get("resumeCount"),
                })
            self.publisher.activity(saved, "AI execution interpreted", f"Execution session {session_id} produced {len(artifacts)} structured artifacts.")
            return saved
        except Exception as exc:
            session["status"] = "Failed"
            session["lastCheckpoint"] = "ResponseInterpretationFailed"
            session["completedAt"] = _now()
            session["duration"] = _elapsed_ms(session["startedAt"])
            session["warnings"] = list(dict.fromkeys([*session["warnings"], str(exc)]))
            session["lastFailure"] = _failure("RuntimeFailure", str(exc), True)
            response_record["disposition"] = "Failed"
            session["lastResponseDisposition"] = "Failed"
            session["diagnostics"] = build_diagnostics(session)
            self.repository.save(session)
            self.publisher.publish("ExecutionFailed", session, {"reason": str(exc)})
            self.publisher.activity(session, "AI execution failed", str(exc))
            raise

    def retry(self, session_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            session = self._required(session_id)
            if session["status"] not in RECOVERABLE_SESSION_STATUSES:
                raise ValueError(f"Execution session cannot be retried from {session['status']}.")
            if session["status"] == "Failed" and (session.get("lastFailure") or {}).get("retryable") is False:
                raise ValueError("Execution failure is not retryable.")
            recovery = session.setdefault("recovery", {"retryCount": 0, "resumeCount": 0, "history": []})
            if int(recovery.get("retryCount") or 0) >= int(session.get("maxRetries") or 0):
                raise ValueError("Execution retry limit reached.")
            previous = session["status"]
            recovery["retryCount"] = int(recovery.get("retryCount") or 0) + 1
            session["attempt"] = int(session.get("attempt") or 1) + 1
            _reopen(session, "RetryRequested", reason or "Execution retry requested.")
            _transition(session, "Retry", previous, session["status"], reason)
            session["diagnostics"] = build_diagnostics(session)
            saved = self.repository.save(session)
            self.publisher.publish("ExecutionRetried", saved, {
                "attempt": saved["attempt"],
                "retryCount": recovery["retryCount"],
                "reason": reason,
                "providerInvoked": False,
            })
            self.publisher.activity(saved, "AI execution retry requested", reason or "Waiting for a new provider callback.")
            return saved

    def resume(self, session_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            session = self._required(session_id)
            if session["status"] not in RECOVERABLE_SESSION_STATUSES:
                raise ValueError(f"Execution session cannot be resumed from {session['status']}.")
            if session["status"] == "Failed" and (session.get("lastFailure") or {}).get("retryable") is False:
                raise ValueError("Execution failure is not resumable.")
            previous = session["status"]
            checkpoint = str(session.get("lastCheckpoint") or previous)
            recovery = session.setdefault("recovery", {"retryCount": 0, "resumeCount": 0, "history": []})
            recovery["resumeCount"] = int(recovery.get("resumeCount") or 0) + 1
            _reopen(session, "Resumed", reason or f"Resumed from {checkpoint}.")
            session["resumeFromCheckpoint"] = checkpoint
            _transition(session, "Resume", previous, session["status"], reason, {"checkpoint": checkpoint})
            session["diagnostics"] = build_diagnostics(session)
            saved = self.repository.save(session)
            self.publisher.publish("ExecutionResumed", saved, {
                "attempt": saved["attempt"],
                "resumeCount": recovery["resumeCount"],
                "checkpoint": checkpoint,
                "reason": reason,
                "providerInvoked": False,
            })
            self.publisher.activity(saved, "AI execution resumed", reason or f"Resumed from {checkpoint}.")
            return saved

    def timeout(self, session_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            session = self._required(session_id)
            if session["status"] == "TimedOut":
                session["lastOperationDisposition"] = "IdempotentReplay"
                return self.repository.save(session)
            if session["status"] in TERMINAL_SESSION_STATUSES:
                raise ValueError(f"Execution session is already {session['status']}.")
            previous = session["status"]
            session["status"] = "TimedOut"
            session["completedAt"] = _now()
            session["duration"] = _elapsed_ms(session["startedAt"])
            session["lastCheckpoint"] = "TimedOut"
            session["lastFailure"] = _failure("Timeout", reason or "Execution exceeded its allowed duration.", True)
            session["warnings"] = list(dict.fromkeys([*session.get("warnings", []), session["lastFailure"]["reason"]]))
            session["lastOperationDisposition"] = "TimedOut"
            _transition(session, "Timeout", previous, "TimedOut", reason)
            session["diagnostics"] = build_diagnostics(session)
            saved = self.repository.save(session)
            self.publisher.publish("ExecutionTimedOut", saved, {
                "reason": session["lastFailure"]["reason"],
                "retryable": True,
            })
            self.publisher.activity(saved, "AI execution timed out", session["lastFailure"]["reason"])
            return saved

    def report_failure(self, session_id: str, failure: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._required(session_id)
            if not isinstance(failure, dict):
                raise ValueError("Failure report must be an object.")
            failure_type = str(failure.get("type") or "RuntimeFailure")
            if failure_type not in FAILURE_TYPES - {"Timeout"}:
                raise ValueError("Failure type must be ProviderFailure, NetworkFailure, or RuntimeFailure.")
            failure_key = str(failure.get("idempotencyKey") or stable_hash({
                "type": failure_type,
                "reason": failure.get("reason"),
                "attempt": session.get("attempt"),
            }))
            previous_failure = session.get("lastFailure") or {}
            if previous_failure.get("failureKey") == failure_key:
                session["lastOperationDisposition"] = "IdempotentReplay"
                return self.repository.save(session)
            if session["status"] in TERMINAL_SESSION_STATUSES and session["status"] != "Failed":
                raise ValueError(f"Execution session is already {session['status']}.")
            previous = session["status"]
            session["status"] = "Failed"
            session["completedAt"] = _now()
            session["duration"] = _elapsed_ms(session["startedAt"])
            session["lastCheckpoint"] = failure_type
            session["lastFailure"] = _failure(
                failure_type,
                str(failure.get("reason") or f"{failure_type} reported."),
                bool(failure.get("retryable", True)),
                failure_key,
            )
            session["warnings"] = list(dict.fromkeys([*session.get("warnings", []), session["lastFailure"]["reason"]]))
            session["lastOperationDisposition"] = "FailureRecorded"
            _transition(session, failure_type, previous, "Failed", session["lastFailure"]["reason"])
            session["diagnostics"] = build_diagnostics(session)
            saved = self.repository.save(session)
            self.publisher.publish("ExecutionFailed", saved, {
                "reason": session["lastFailure"]["reason"],
                "failureType": failure_type,
                "retryable": session["lastFailure"]["retryable"],
            })
            self.publisher.activity(saved, f"AI execution {failure_type}", session["lastFailure"]["reason"])
            return saved

    def cancel(self, session_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            return self._cancel_locked(session_id, reason)

    def _cancel_locked(self, session_id: str, reason: str = "") -> dict[str, Any]:
        session = self._required(session_id)
        if session["status"] == "Cancelled":
            session["lastOperationDisposition"] = "IdempotentReplay"
            return self.repository.save(session)
        if session["status"] in TERMINAL_SESSION_STATUSES:
            raise ValueError(f"Execution session is already {session['status']}.")
        previous = session["status"]
        session["status"] = "Cancelled"
        session["completedAt"] = _now()
        session["duration"] = _elapsed_ms(session["startedAt"])
        if reason:
            session["warnings"] = list(dict.fromkeys([*session["warnings"], reason]))
        session["lastCheckpoint"] = "Cancelled"
        session["lastOperationDisposition"] = "Cancelled"
        _transition(session, "Cancel", previous, "Cancelled", reason)
        session["diagnostics"] = build_diagnostics(session)
        saved = self.repository.save(session)
        self.publisher.publish("ExecutionCancelled", saved, {"reason": reason})
        self.publisher.activity(saved, "AI execution cancelled", reason or "The execution session was cancelled.")
        return saved

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self.repository.get(session_id)

    def summary(self, session_id: str) -> dict[str, Any] | None:
        session = self.get(session_id)
        if not session:
            return None
        diff = session.get("engineeringDiff") or {}
        return {
            "sessionId": session["sessionId"],
            "status": session["status"],
            "provider": session["provider"],
            "model": session["model"],
            "executionPlanVersion": session["executionPlanVersion"],
            "executionPackageVersion": session["executionPackageVersion"],
            "repositorySnapshotVersion": session["repositorySnapshotVersion"],
            "artifactCount": len(session.get("artifacts") or []),
            "engineeringDiff": deepcopy(diff.get("summary") or {}),
            "pendingDownstreamIntents": [value["type"] for value in session.get("downstreamIntents") or [] if not value.get("invoked")],
            "confidence": session["confidence"],
            "warnings": list(session["warnings"]),
            "duration": session["duration"],
            "correlationId": session["correlationId"],
            "attempt": int(session.get("attempt") or 1),
            "lastCheckpoint": str(session.get("lastCheckpoint") or ""),
            "lastResponseDisposition": str(session.get("lastResponseDisposition") or ""),
            "duplicateResponseCount": int(session.get("duplicateResponseCount") or 0),
            "partialResponseCount": len(session.get("partialResponses") or []),
            "retryCount": int((session.get("recovery") or {}).get("retryCount") or 0),
            "resumeCount": int((session.get("recovery") or {}).get("resumeCount") or 0),
            "recoverable": session["status"] in RECOVERABLE_SESSION_STATUSES,
        }

    def diagnostics(self, session_id: str) -> dict[str, Any] | None:
        session = self.get(session_id)
        return deepcopy(session.get("diagnostics")) if session else None

    def _required(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        if not session:
            raise KeyError(session_id)
        return session


def _validate_start(request: dict[str, Any]) -> None:
    if not isinstance(request, dict):
        raise ValueError("Execution runtime request must be an object.")
    required = ("executionPlanVersion", "executionPackageVersion", "provider", "model")
    missing = [field for field in required if not str(request.get(field) or "").strip()]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}.")
    if not str(request.get("executionPromptId") or "").strip() and not isinstance(request.get("executionPrompt"), dict):
        raise ValueError("executionPromptId or executionPrompt is required.")
    try:
        retries = int(request.get("maxRetries", 3))
    except (TypeError, ValueError) as exc:
        raise ValueError("maxRetries must be an integer between 0 and 10.") from exc
    if retries < 0 or retries > 10:
        raise ValueError("maxRetries must be an integer between 0 and 10.")


def _result(
    session: dict[str, Any],
    interpreted: dict[str, Any],
    provider_response: Any,
    metadata: dict[str, Any],
    operation_started: float,
) -> dict[str, Any]:
    core = {"sessionId": session["sessionId"], "response": interpreted["structuredResponse"]}
    envelope_usage = provider_response.get("usage") if isinstance(provider_response, dict) and isinstance(provider_response.get("usage"), dict) else {}
    return {
        "resultId": f"execution_result_{stable_hash(core)[:12]}",
        "sessionId": session["sessionId"],
        "provider": session["provider"],
        "model": session["model"],
        "responseType": interpreted["responseType"],
        "status": "Completed",
        "rawResponse": deepcopy(interpreted["rawResponse"]),
        "structuredResponse": deepcopy(interpreted["structuredResponse"]),
        "warnings": list(interpreted["warnings"]),
        "errors": [],
        "confidence": interpreted["confidence"],
        "tokenUsage": deepcopy(metadata.get("tokenUsage") or envelope_usage),
        "duration": float(metadata.get("durationMs") or round((time.perf_counter() - operation_started) * 1000, 2)),
    }


def _pr_candidate(session: dict[str, Any], result: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    core = {"sessionId": session["sessionId"], "resultId": result["resultId"], "diffId": diff["diffId"]}
    return {
        "candidateId": f"pr_candidate_{stable_hash(core)[:12]}",
        "sessionId": session["sessionId"],
        "resultId": result["resultId"],
        "engineeringDiffId": diff["diffId"],
        "status": "Draft",
        "created": False,
        "title": "AI execution outcome review",
        "artifactIds": list(diff["artifactIds"]),
        "correlationId": session["correlationId"],
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at)
        return round(max(0.0, (datetime.now(timezone.utc) - started).total_seconds() * 1000), 2)
    except (TypeError, ValueError):
        return 0.0


def _response_key(provider_response: Any, metadata: dict[str, Any]) -> str:
    supplied = str(metadata.get("idempotencyKey") or metadata.get("responseId") or "").strip()
    return supplied or f"response_{stable_hash(provider_response)[:20]}"


def _is_partial_response(provider_response: Any, metadata: dict[str, Any]) -> bool:
    if metadata.get("partial") is True:
        return True
    if not isinstance(provider_response, dict):
        return False
    choices = provider_response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return False
    finish_reason = str(choices[0].get("finish_reason") or choices[0].get("finishReason") or "").casefold()
    return finish_reason in {"length", "max_tokens", "incomplete"}


def _failure(failure_type: str, reason: str, retryable: bool, failure_key: str = "") -> dict[str, Any]:
    return {
        "type": failure_type,
        "reason": reason,
        "retryable": retryable,
        "failureKey": failure_key or f"failure_{stable_hash({'type': failure_type, 'reason': reason})[:20]}",
        "recordedAt": _now(),
    }


def _reopen(session: dict[str, Any], checkpoint: str, reason: str) -> None:
    session["status"] = "AwaitingResponse"
    session["completedAt"] = ""
    session["duration"] = 0.0
    session["attemptStartedAt"] = _now()
    session["lastCheckpoint"] = checkpoint
    session["lastOperationDisposition"] = checkpoint
    session["diagnostics"] = build_diagnostics(session)


def _transition(
    session: dict[str, Any],
    action: str,
    from_status: str,
    to_status: str,
    reason: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    recovery = session.setdefault("recovery", {"retryCount": 0, "resumeCount": 0, "history": []})
    recovery.setdefault("history", []).append({
        "action": action,
        "fromStatus": from_status,
        "toStatus": to_status,
        "reason": reason,
        "attempt": int(session.get("attempt") or 1),
        "at": _now(),
        "details": deepcopy(details or {}),
    })
