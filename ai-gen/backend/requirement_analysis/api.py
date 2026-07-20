"""Requirement Analysis APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from .service import RequirementAnalysisService


def build_requirement_analysis_router(service: RequirementAnalysisService) -> APIRouter:
    router = APIRouter(prefix="/requirements", tags=["HEI Requirement Analysis"])

    @router.post("/analyze")
    def analyze(request: dict[str, Any] = Body(...)):
        requirement_id = str(request.get("requirementId") or request.get("requirementContextId") or "").strip()
        if not requirement_id:
            return JSONResponse(status_code=400, content={"error": {"code": "requirement_id_required", "message": "Requirement ID is required."}})
        try:
            return service.analyze(requirement_id, force=bool(request.get("force")))
        except ValueError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_not_found", "message": str(error)}})

    @router.get("/{requirement_id}/analysis")
    def get_analysis(requirement_id: str):
        value = service.get(requirement_id)
        if value is None:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_analysis_not_found", "message": "Requirement analysis was not found."}})
        return value

    @router.post("/{requirement_id}/analysis/approve")
    def approve(requirement_id: str, request: dict[str, Any] = Body(default={})):
        try:
            return service.approve(requirement_id, str(request.get("actor") or "HEI User"))
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "requirement_review_not_approvable", "message": str(error)}})

    @router.post("/{requirement_id}/analysis/cancel")
    def cancel(requirement_id: str, request: dict[str, Any] = Body(default={})):
        try:
            return service.cancel(requirement_id, str(request.get("actor") or "HEI User"))
        except ValueError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_analysis_not_found", "message": str(error)}})

    @router.post("/{requirement_id}/analysis/edit")
    def edit(requirement_id: str, request: dict[str, Any] = Body(...)):
        try:
            return service.edit(requirement_id, request)
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_requirement_edit", "message": str(error)}})

    @router.post("/{requirement_id}/analysis/reanalyze")
    def reanalyze(requirement_id: str):
        try:
            return service.analyze(requirement_id, force=True)
        except ValueError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_not_found", "message": str(error)}})

    return router
