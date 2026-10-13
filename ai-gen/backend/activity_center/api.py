"""Activity Center REST API."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .service import ActivityCenterError


def build_activity_center_router(service) -> APIRouter:
    router = APIRouter(prefix="/activity", tags=["Activity Center"])

    def call(action):
        try:
            return action()
        except ActivityCenterError as error:
            return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": str(error)}})

    @router.get("")
    def activity(
        search: str = "",
        category: str = "",
        status: str = "",
        source: str = "",
        correlation_id: str = Query(default="", alias="correlationId"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=250),
    ):
        return service.list(search=search, category=category, status=status, source=source, correlation_id=correlation_id, offset=offset, limit=limit)

    # Static correlation route must be declared before the activity-id route.
    @router.get("/correlation/{correlation_id}")
    def correlation(correlation_id: str):
        return call(lambda: service.correlation(correlation_id))

    @router.post("/{activity_id}/replay")
    def replay(activity_id: str):
        return call(lambda: service.replay(activity_id))

    @router.get("/{activity_id}")
    def detail(activity_id: str):
        return call(lambda: service.get(activity_id))

    return router
