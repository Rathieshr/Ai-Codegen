"""FastAPI routes for the context orchestrator foundation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import ContextRequest


def build_context_orchestration_router(orchestrator) -> APIRouter:
    router = APIRouter(prefix="/context", tags=["Context Orchestration"])

    @router.post("/orchestrate")
    def orchestrate(payload: dict) -> dict:
        try: return orchestrator.orchestrate(ContextRequest.from_dict(payload))
        except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/requests/{request_id}")
    def get_request(request_id: str) -> dict:
        result = orchestrator.get(request_id)
        if not result: raise HTTPException(status_code=404, detail="Context request not found.")
        return result

    @router.get("/requests/{request_id}/diagnostics")
    def get_diagnostics(request_id: str) -> dict:
        result = orchestrator.diagnostics(request_id)
        if not result: raise HTTPException(status_code=404, detail="Context request not found.")
        return result

    @router.get("/health")
    def health() -> dict: return orchestrator.health()

    return router
