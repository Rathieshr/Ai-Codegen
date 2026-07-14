"""Planning Center REST API."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class PlanningDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = ""


def build_planning_center_router(service) -> APIRouter:
    router = APIRouter(prefix="/planning", tags=["Planning Center"])

    @router.get("")
    def list_planning(
        project_id: str = Query(default="", alias="projectId"), search: str = "", item_type: str = Query(default="", alias="type"),
        status: str = "", readiness: str = "", offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250),
    ):
        return service.list(project_id=project_id, search=search, item_type=item_type, status=status, readiness=readiness, offset=offset, limit=limit)

    @router.get("/recommendations")
    def recommendations(project_id: str = Query(default="", alias="projectId"), status: str = ""):
        return service.recommendations(project_id, status)

    @router.get("/{planning_id}")
    def details(planning_id: str, project_id: str = Query(default="", alias="projectId")):
        try:
            return service.get(planning_id, project_id)
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})

    @router.post("/{planning_id}/approve")
    def approve(planning_id: str, request: PlanningDecisionRequest | None = None):
        try:
            return service.approve(planning_id, request.actor if request else "")
        except (LookupError, ValueError) as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})

    @router.post("/{planning_id}/reject")
    def reject(planning_id: str, request: PlanningDecisionRequest | None = None):
        try:
            return service.reject(planning_id, request.actor if request else "")
        except (LookupError, ValueError) as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})

    return router
