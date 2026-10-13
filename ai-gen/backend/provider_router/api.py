"""Provider Router REST API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_provider_router_api(service, manifest_service=None) -> APIRouter:
    router = APIRouter(prefix="/provider-router", tags=["Provider Router"])

    @router.post("/route")
    def route(payload: dict) -> dict:
        manifest = payload.get("executionManifest")
        manifest_id = str(payload.get("executionManifestId") or payload.get("manifestId") or "")
        if not isinstance(manifest, dict) and manifest_id and manifest_service:
            manifest = manifest_service.get(manifest_id)
            if not isinstance(manifest, dict):
                raise HTTPException(status_code=404, detail="Execution Manifest not found.")
        if not isinstance(manifest, dict):
            raise HTTPException(status_code=422, detail="executionManifest or executionManifestId is required.")
        try:
            return service.route(
                manifest,
                execution_mode=str(payload.get("executionMode") or "Implementation"),
                repository_mode=str(payload.get("repositoryMode") or ""),
                target_task=payload.get("targetTask"),
                user_preference=payload.get("userPreference"),
                available_models=payload.get("availableModels") if isinstance(payload.get("availableModels"), list) else None,
                correlation_id=str(payload.get("correlationId") or ""),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/decisions/{routing_id}")
    def get(routing_id: str) -> dict:
        value = service.get(routing_id)
        if not value:
            raise HTTPException(status_code=404, detail="Provider routing decision not found.")
        return value

    @router.get("/decisions/{routing_id}/diagnostics")
    def diagnostics(routing_id: str) -> dict:
        value = service.diagnostics(routing_id)
        if not value:
            raise HTTPException(status_code=404, detail="Provider routing decision not found.")
        return value

    return router
