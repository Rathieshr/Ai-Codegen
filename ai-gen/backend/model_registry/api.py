"""Read-only Model Registry REST API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_model_registry_router(registry) -> APIRouter:
    router = APIRouter(prefix="/models", tags=["Model Registry"])

    @router.get("")
    def list_models() -> dict:
        models = registry.list()
        return {"models": models, "count": len(models)}

    @router.get("/{model_id}")
    def get_model(model_id: str) -> dict:
        profile = registry.get(model_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Model profile not found.")
        return profile

    return router
