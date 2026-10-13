"""Planning Center REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class PlanningDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = ""
    comments: str = ""
    expectedVersion: int | None = None


class PlanningRollbackRequest(PlanningDecisionRequest):
    targetVersion: int


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

    @router.put("/node")
    def update_node(request: dict[str, Any] = Body(...), actor: str = Query(default="")):
        try:
            return service.update_node(request, actor or str(request.get("actor") or ""))
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_node_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_node_conflict", "message": str(error)}})

    @router.post("/node/regenerate")
    def regenerate_node(request: dict[str, Any] = Body(...), actor: str = Query(default="")):
        try:
            return service.regenerate_node(request, actor or str(request.get("actor") or ""))
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_node_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_regeneration_failed", "message": str(error)}})

    @router.delete("/node")
    def delete_node(request: dict[str, Any] = Body(...), actor: str = Query(default="")):
        try:
            return service.delete_node(request, actor or str(request.get("actor") or ""))
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_node_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_node_conflict", "message": str(error)}})

    @router.get("/{planning_id}/overview")
    def overview(planning_id: str, project_id: str = Query(default="", alias="projectId")):
        try:
            return service.overview(planning_id, project_id)
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})

    @router.get("/{planning_id}/hierarchy")
    def hierarchy(planning_id: str, project_id: str = Query(default="", alias="projectId")):
        try:
            return service.hierarchy(planning_id, project_id)
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})

    @router.get("/{planning_id}")
    def details(planning_id: str, project_id: str = Query(default="", alias="projectId")):
        try:
            return service.get(planning_id, project_id)
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})

    @router.put("/{planning_id}")
    def update(planning_id: str, request: dict[str, Any] = Body(...), actor: str = Query(default="")):
        try:
            return service.update(planning_id, request, actor or str(request.get("actor") or ""))
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_update_conflict", "message": str(error)}})

    @router.post("/{planning_id}/save")
    def save(planning_id: str, request: dict[str, Any] = Body(default_factory=dict), actor: str = Query(default="")):
        try:
            return service.save(planning_id, request, actor or str(request.get("actor") or ""))
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_update_conflict", "message": str(error)}})

    @router.post("/{planning_id}/approve")
    def approve(planning_id: str, request: PlanningDecisionRequest | None = None):
        try:
            return service.approve(
                planning_id, request.actor if request else "", request.comments if request else "",
                request.expectedVersion if request else None,
            )
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_transition_conflict", "message": str(error)}})

    @router.post("/{planning_id}/reject")
    def reject(planning_id: str, request: PlanningDecisionRequest | None = None):
        try:
            return service.reject(
                planning_id, request.actor if request else "", request.comments if request else "",
                request.expectedVersion if request else None,
            )
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_transition_conflict", "message": str(error)}})

    @router.post("/{planning_id}/request-changes")
    def request_changes(planning_id: str, request: PlanningDecisionRequest):
        try:
            return service.request_changes(planning_id, request.actor, request.comments, request.expectedVersion)
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_transition_conflict", "message": str(error)}})

    @router.post("/{planning_id}/publish")
    def publish(planning_id: str, request: PlanningDecisionRequest | None = None):
        try:
            return service.publish(
                planning_id, request.actor if request else "", request.comments if request else "",
                request.expectedVersion if request else None,
            )
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_transition_conflict", "message": str(error)}})

    @router.post("/{planning_id}/rollback")
    def rollback(planning_id: str, request: PlanningRollbackRequest):
        try:
            return service.rollback(
                planning_id, request.targetVersion, request.actor, request.comments, request.expectedVersion,
            )
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "planning_transition_conflict", "message": str(error)}})

    @router.get("/{planning_id}/history")
    def history(planning_id: str):
        try:
            return service.history(planning_id)
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_item_not_found", "message": str(error)}})

    return router
