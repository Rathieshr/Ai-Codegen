"""Recovery commands for persisted AI execution sessions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_runtime_recovery_router(service) -> APIRouter:
    router = APIRouter(prefix="/execution-runtime", tags=["Runtime Recovery"])

    @router.post("/{session_id}/retry")
    def retry(session_id: str, payload: dict | None = None) -> dict:
        return _call(service.retry, session_id, str((payload or {}).get("reason") or ""))

    @router.post("/{session_id}/resume")
    def resume(session_id: str, payload: dict | None = None) -> dict:
        return _call(service.resume, session_id, str((payload or {}).get("reason") or ""))

    @router.post("/{session_id}/timeout")
    def timeout(session_id: str, payload: dict | None = None) -> dict:
        return _call(service.timeout, session_id, str((payload or {}).get("reason") or ""))

    @router.post("/{session_id}/failure")
    def failure(session_id: str, payload: dict) -> dict:
        return _call(service.report_failure, session_id, payload)

    return router


def _call(operation, session_id: str, value) -> dict:
    try:
        return operation(session_id, value)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execution session not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
