"""REST API for the Requirement Summary planning boundary."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse


def build_requirement_planning_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/planning", tags=["Requirement Planning Integration"])

    def call(action: Any):
        try:
            return action()
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_source_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_requirement_planning", "message": str(error)}})

    @router.post("/from-requirement")
    def from_requirement(request: dict[str, Any] = Body(...)):
        return call(lambda: service.from_requirement(request))

    @router.post("/preview")
    def preview(request: dict[str, Any] = Body(...)):
        return call(lambda: service.preview(request))

    @router.post("/generate")
    def generate(request: dict[str, Any] = Body(...)):
        return call(lambda: service.generate(request))

    return router
