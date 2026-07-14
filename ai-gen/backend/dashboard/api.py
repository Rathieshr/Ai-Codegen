"""Engineering Command Center dashboard APIs."""

from __future__ import annotations

from fastapi import APIRouter, Query


def build_dashboard_router(service) -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["Engineering Command Center"])

    @router.get("/overview")
    def overview(project_id: str = Query(default="", alias="projectId")):
        return service.overview(project_id)

    @router.get("/widgets")
    def widgets(project_id: str = Query(default="", alias="projectId")):
        return service.widgets(project_id)

    @router.get("/summary")
    def summary(project_id: str = Query(default="", alias="projectId")):
        return service.summary(project_id)

    return router
