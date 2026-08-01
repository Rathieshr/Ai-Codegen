"""Requirement Refinement APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from .service import RequirementRefinementService


def build_requirement_refinement_router(service: RequirementRefinementService) -> APIRouter:
    router = APIRouter(prefix="/requirements", tags=["HEI Requirement Refinement"])

    @router.post("/{requirement_id}/refine")
    def refine(requirement_id: str, request: dict[str, Any] = Body(default={})):
        try:
            return service.refine(requirement_id, force=bool(request.get("force")))
        except ValueError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_not_found", "message": str(error)}})

    @router.get("/{requirement_id}/refinement")
    def get_refinement(requirement_id: str):
        value = service.get(requirement_id)
        if value is None:
            return JSONResponse(status_code=404, content={"error": {"code": "refinement_not_found", "message": "Requirement refinement was not found."}})
        return value

    @router.post("/{requirement_id}/refinement/accept")
    def accept(requirement_id: str, request: dict[str, Any] = Body(default={})):
        try:
            return service.accept(requirement_id, str(request.get("actor") or "HEI User"))
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "refinement_not_accepted", "message": str(error)}})

    @router.put("/{requirement_id}/refinement")
    def edit(requirement_id: str, request: dict[str, Any] = Body(...)):
        try:
            return service.edit(requirement_id, str(request.get("refinedRequirement") or ""), str(request.get("actor") or "HEI User"))
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_refinement", "message": str(error)}})

    @router.post("/{requirement_id}/refinement/regenerate")
    def regenerate(requirement_id: str):
        try:
            return service.refine(requirement_id, force=True)
        except ValueError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_not_found", "message": str(error)}})

    @router.post("/{requirement_id}/refinement/skip")
    def skip(requirement_id: str, request: dict[str, Any] = Body(default={})):
        try:
            return service.skip(requirement_id, str(request.get("actor") or "HEI User"))
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "refinement_not_skipped", "message": str(error)}})

    return router
