"""Read-only Runtime Observability API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_runtime_observability_router(service) -> APIRouter:
    router = APIRouter(prefix="/runtime/traces", tags=["Runtime Observability"])

    @router.get("")
    def list_traces(status: str = "", provider: str = "", limit: int = 100) -> dict:
        return service.list(status=status, provider=provider, limit=limit)

    @router.get("/{trace_id}")
    def get_trace(trace_id: str) -> dict:
        value = service.get(trace_id)
        if value is None:
            raise HTTPException(status_code=404, detail="Runtime trace not found.")
        return value

    return router
