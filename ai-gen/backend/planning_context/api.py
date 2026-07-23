"""Planning Context Engine REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse


def build_planning_context_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/planning/context", tags=["Planning Context Engine"])

    def call(action: Any):
        try:
            return action()
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_context_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_planning_context", "message": str(error)}})

    @router.post("/build")
    def build(request: dict[str, Any] = Body(...)):
        return call(lambda: service.build(request))

    @router.get("/{context_id}")
    def get(context_id: str):
        return call(lambda: service.get(context_id))

    @router.post("/refresh")
    def refresh(request: dict[str, Any] = Body(...)):
        return call(lambda: service.refresh(request))

    @router.post("/classify")
    def classify(request: dict[str, Any] = Body(...)):
        return call(lambda: service.classify(request))

    @router.post("/analyze")
    def analyze(request: dict[str, Any] = Body(...)):
        return call(lambda: service.analyze(request))

    return router
