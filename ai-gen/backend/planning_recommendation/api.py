"""Planning Recommendation Engine REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse


def build_planning_recommendation_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/planning/recommendation", tags=["Planning Recommendation Engine"])

    def call(action: Any):
        try:
            return action()
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_recommendation_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_planning_recommendation", "message": str(error)}})

    @router.post("")
    def build(request: dict[str, Any] = Body(...)):
        return call(lambda: service.build(request))

    @router.post("/readiness")
    def readiness(request: dict[str, Any] = Body(...)):
        return call(lambda: service.calculate_readiness(request))

    @router.post("/impact")
    def impact(request: dict[str, Any] = Body(...)):
        return call(lambda: service.calculate_impact(request))

    @router.post("/reuse")
    def reuse(request: dict[str, Any] = Body(...)):
        return call(lambda: service.get_reuse_suggestions(request))

    @router.get("/{recommendation_id}")
    def get(recommendation_id: str):
        return call(lambda: service.get(recommendation_id))

    @router.get("/{recommendation_id}/alternatives")
    def alternatives(recommendation_id: str):
        return call(lambda: service.get_alternatives(recommendation_id))

    @router.get("/{recommendation_id}/export")
    def export(recommendation_id: str):
        return call(lambda: service.export_report(recommendation_id))

    @router.post("/regenerate")
    def regenerate(request: dict[str, Any] = Body(...)):
        return call(lambda: service.regenerate(request))

    @router.post("/approve")
    def approve(request: dict[str, Any] = Body(...)):
        return call(lambda: service.approve(request))

    @router.post("/override")
    def override(request: dict[str, Any] = Body(...)):
        return call(lambda: service.override(request))

    return router
