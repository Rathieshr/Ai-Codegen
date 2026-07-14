"""HTTP API for immutable Execution Manifests."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_execution_manifest_router(service, package_service=None) -> APIRouter:
    router = APIRouter(prefix="/execution-manifests", tags=["Execution Manifests"])

    @router.post("/build")
    def build(payload: dict) -> dict:
        package = payload.get("executionPackage")
        package_id = str(payload.get("executionPackageId") or payload.get("packageId") or "")
        if not isinstance(package, dict) and package_id and package_service:
            package = package_service.get(package_id)
            if not isinstance(package, dict):
                raise HTTPException(status_code=404, detail="Execution Package not found.")
        if not isinstance(package, dict):
            raise HTTPException(status_code=422, detail="executionPackage or executionPackageId is required.")
        try:
            return service.build(package, str(payload.get("correlationId") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{manifest_id}")
    def get(manifest_id: str) -> dict:
        value = service.get(manifest_id)
        if not value:
            raise HTTPException(status_code=404, detail="Execution Manifest not found.")
        return value

    @router.get("/{manifest_id}/summary")
    def summary(manifest_id: str) -> dict:
        value = service.summary(manifest_id)
        if not value:
            raise HTTPException(status_code=404, detail="Execution Manifest not found.")
        return value

    @router.get("/{manifest_id}/diagnostics")
    def diagnostics(manifest_id: str) -> dict:
        value = service.diagnostics(manifest_id)
        if not value:
            raise HTTPException(status_code=404, detail="Execution Manifest not found.")
        return value

    return router
