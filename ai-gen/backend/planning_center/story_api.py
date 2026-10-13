"""Story Detail Drawer REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse


def build_story_detail_router(service) -> APIRouter:
    router = APIRouter(prefix="/story", tags=["Story Detail"])

    @router.get("/{story_id}")
    def get_story(story_id: str, project_id: str = Query(default="", alias="projectId")):
        return _call(lambda: service.get(story_id, project_id))

    @router.put("/{story_id}")
    def update_story(story_id: str, request: dict[str, Any] = Body(...), actor: str = Query(default=""), project_id: str = Query(default="", alias="projectId")):
        return _call(lambda: service.update(story_id, request, actor or str(request.get("actor") or ""), project_id))

    @router.post("/{story_id}/regenerate")
    def regenerate_story(story_id: str, request: dict[str, Any] = Body(default_factory=dict), actor: str = Query(default=""), project_id: str = Query(default="", alias="projectId")):
        return _call(lambda: service.regenerate(story_id, actor or str(request.get("actor") or ""), project_id))

    @router.post("/{story_id}/regenerate-tasks")
    def regenerate_tasks(story_id: str, request: dict[str, Any] = Body(default_factory=dict), actor: str = Query(default=""), project_id: str = Query(default="", alias="projectId")):
        return _call(lambda: service.regenerate_tasks(story_id, actor or str(request.get("actor") or ""), project_id))

    @router.post("/{story_id}/generate-tests")
    def generate_tests(story_id: str, request: dict[str, Any] = Body(default_factory=dict), actor: str = Query(default=""), project_id: str = Query(default="", alias="projectId")):
        return _call(lambda: service.generate_tests(story_id, actor or str(request.get("actor") or ""), project_id))

    @router.delete("/{story_id}")
    def delete_story(story_id: str, actor: str = Query(default="")):
        return _call(lambda: service.delete(story_id, actor))

    return router


def _call(operation):
    try:
        return operation()
    except LookupError as error:
        return JSONResponse(status_code=404, content={"error": {"code": "story_not_found", "message": str(error)}})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"error": {"code": "story_conflict", "message": str(error)}})
