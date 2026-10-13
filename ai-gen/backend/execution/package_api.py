"""HTTP API for canonical Execution Packages."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .package_models import ExecutionRequest


def build_execution_package_router(service) -> APIRouter:
    router = APIRouter(prefix="/execution-packages", tags=["Execution Packages"])

    @router.post("/build")
    def build(payload: dict) -> dict:
        capsule = payload.get("contextCapsule")
        if not isinstance(capsule, dict): raise HTTPException(status_code=422, detail="contextCapsule is required.")
        try: return service.build(capsule, ExecutionRequest.from_dict(payload.get("executionRequest") or {}), str(payload.get("correlationId") or ""))
        except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{package_id}")
    def get(package_id: str) -> dict:
        value = service.get(package_id)
        if not value: raise HTTPException(status_code=404, detail="Execution package not found.")
        return value

    @router.get("/{package_id}/summary")
    def summary(package_id: str) -> dict:
        value = service.summary(package_id)
        if not value: raise HTTPException(status_code=404, detail="Execution package not found.")
        return value

    @router.get("/{package_id}/diagnostics")
    def diagnostics(package_id: str) -> dict:
        value = service.diagnostics(package_id)
        if not value: raise HTTPException(status_code=404, detail="Execution package not found.")
        return value

    return router
