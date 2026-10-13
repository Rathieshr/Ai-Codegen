"""HTTP contract for AI Execution Runtime sessions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_execution_runtime_router(service) -> APIRouter:
    router = APIRouter(prefix="/execution-runtime", tags=["AI Execution Runtime"])

    @router.post("/start")
    def start(payload: dict) -> dict:
        try:
            return service.start(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/{session_id}/response")
    def response(session_id: str, payload: dict) -> dict:
        if "providerResponse" not in payload:
            raise HTTPException(status_code=422, detail="providerResponse is required.")
        try:
            return service.receive_response(session_id, payload["providerResponse"], payload.get("metadata"))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Execution session not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/{session_id}/cancel")
    def cancel(session_id: str, payload: dict | None = None) -> dict:
        try:
            return service.cancel(session_id, str((payload or {}).get("reason") or ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Execution session not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/{session_id}")
    def get(session_id: str) -> dict:
        value = service.get(session_id)
        if not value:
            raise HTTPException(status_code=404, detail="Execution session not found.")
        return value

    @router.get("/{session_id}/summary")
    def summary(session_id: str) -> dict:
        value = service.summary(session_id)
        if not value:
            raise HTTPException(status_code=404, detail="Execution session not found.")
        return value

    @router.get("/{session_id}/diagnostics")
    def diagnostics(session_id: str) -> dict:
        value = service.diagnostics(session_id)
        if value is None:
            raise HTTPException(status_code=404, detail="Execution session not found.")
        return value

    return router
