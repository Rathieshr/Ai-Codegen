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
        except PermissionError as error:
            return JSONResponse(status_code=403, content={"error": {"code": "planning_approval_required", "message": str(error)}})
        except RuntimeError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_sync_conflict", "message": str(error)}})

    @router.post("/from-requirement")
    def from_requirement(request: dict[str, Any] = Body(...)):
        return call(lambda: service.from_requirement(request))

    @router.post("/preview")
    def preview(request: dict[str, Any] = Body(...)):
        return call(lambda: service.preview(request))

    @router.post("/generate")
    def generate(request: dict[str, Any] = Body(...)):
        return call(lambda: service.generate(request))

    @router.post("/context")
    def context(request: dict[str, Any] = Body(...)):
        return call(lambda: service.context(request))

    @router.post("/analyze")
    def analyze(request: dict[str, Any] = Body(...)):
        return call(lambda: service.analyze(request))

    @router.post("/recommend")
    def recommend(request: dict[str, Any] = Body(...)):
        return call(lambda: service.recommend(request))

    @router.get("/{planning_pack_id}/diff")
    def planning_diff(planning_pack_id: str):
        return call(lambda: service.diff(planning_pack_id))

    @router.post("/{planning_pack_id}/diff/approve")
    def approve_diff(planning_pack_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.approve_diff(planning_pack_id, request))

    @router.post("/{planning_pack_id}/sync")
    def sync(planning_pack_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.sync(planning_pack_id, request))

    return router
