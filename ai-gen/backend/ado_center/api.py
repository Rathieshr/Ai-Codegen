"""Azure DevOps Center REST API."""

from __future__ import annotations

from fastapi import APIRouter, Query


def build_ado_center_router(service) -> APIRouter:
    router = APIRouter(prefix="/ado", tags=["Azure DevOps Center"])

    @router.get("/dashboard")
    def dashboard(project_id: str = Query(default="", alias="projectId")):
        return service.dashboard(project_id)

    @router.get("/sprint")
    def sprint(project_id: str = Query(default="", alias="projectId"), team_id: str = Query(default="", alias="teamId")):
        return service.sprint(project_id, team_id)

    @router.get("/work-items")
    def work_items(project_id: str = Query(default="", alias="projectId"), search: str = "", state: str = "", item_type: str = Query(default="", alias="type"), offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250)):
        return service.work_items(project_id, search=search, state=state, item_type=item_type, offset=offset, limit=limit)

    @router.get("/prs")
    def pull_requests(project_id: str = Query(default="", alias="projectId"), search: str = "", status: str = "", offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250)):
        return service.pull_requests(project_id, search=search, status=status, offset=offset, limit=limit)

    return router
