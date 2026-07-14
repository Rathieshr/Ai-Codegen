"""Prompt Cache REST API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_prompt_cache_router(service) -> APIRouter:
    router = APIRouter(prefix="/prompt-cache", tags=["Prompt Cache"])

    @router.get("/metrics")
    def metrics() -> dict:
        return service.metrics()

    @router.get("/entries/{cache_key}")
    def get(cache_key: str) -> dict:
        value = service.get(cache_key)
        if not value:
            raise HTTPException(status_code=404, detail="Prompt Cache entry not found.")
        return value

    @router.post("/invalidate")
    def invalidate(payload: dict) -> dict:
        criteria = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
        if not criteria:
            raise HTTPException(status_code=422, detail="At least one invalidation criterion is required.")
        return service.invalidate(
            criteria,
            reason=str(payload.get("reason") or "Manual invalidation"),
            correlation_id=str(payload.get("correlationId") or ""),
        )

    return router
