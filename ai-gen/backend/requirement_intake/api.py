"""Requirement intake APIs for the HEI single hub."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from .ingestion import RequirementIngestionService
from .service import RequirementIntakeService


def build_requirement_intake_router(
    service: RequirementIntakeService,
    ingestion_service: RequirementIngestionService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/requirements", tags=["HEI Requirement Intake"])
    ingestion = ingestion_service or service.ingestion_service

    @router.post("/ingest")
    def ingest(request: dict[str, Any] = Body(...)):
        try:
            return ingestion.ingest(request)
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_requirement_source", "message": str(error)}})

    @router.post("/intake")
    def intake(request: dict[str, Any] = Body(...)):
        try:
            return service.submit(request)
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_requirement", "message": str(error)}})

    @router.get("")
    def requirements(project_id: str = Query(default="", alias="projectId")):
        return service.list(project_id)

    @router.get("/{requirement_id}/status")
    def requirement_status(requirement_id: str):
        value = ingestion.status(requirement_id)
        if value is None:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_not_found", "message": "Requirement was not found."}})
        return value

    @router.get("/{requirement_id}")
    def requirement(requirement_id: str):
        value = ingestion.get(requirement_id) or service.get(requirement_id)
        if value is None:
            return JSONResponse(status_code=404, content={"error": {"code": "requirement_not_found", "message": "Requirement was not found."}})
        return value

    return router
