"""Agent Center REST API."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .service import AgentCenterError


def build_agent_center_router(service) -> APIRouter:
    router = APIRouter(prefix="/agents", tags=["Agent Center"])

    def call(action):
        try:
            return action()
        except AgentCenterError as error:
            return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": str(error)}})

    @router.get("")
    def agents():
        return service.list()

    @router.post("/jobs/{job_id}/retry")
    def retry(job_id: str):
        return call(lambda: service.retry(job_id))

    @router.get("/{agent_id}")
    def agent(agent_id: str):
        return call(lambda: service.get(agent_id))

    @router.get("/{agent_id}/jobs")
    def jobs(agent_id: str, status: str = "", offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250)):
        return call(lambda: service.jobs(agent_id, status=status, offset=offset, limit=limit))

    @router.get("/{agent_id}/health")
    def health(agent_id: str):
        return call(lambda: service.health(agent_id))

    return router
