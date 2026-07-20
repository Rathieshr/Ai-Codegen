"""Task Generation REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse


def build_task_generation_router(service) -> APIRouter:
    router = APIRouter(tags=["Task Generation"])

    @router.post("/story/{story_id}/tasks")
    def create_story_tasks(story_id: str, request: dict[str, Any] = Body(default_factory=dict), actor: str = Query(default="")):
        return _call(lambda: service.create_for_story(story_id, request, actor or str(request.get("actor") or "")))

    @router.put("/task/{task_id}")
    def update_task(task_id: str, request: dict[str, Any] = Body(...), actor: str = Query(default="")):
        return _call(lambda: service.update(task_id, request, actor or str(request.get("actor") or "")))

    @router.delete("/task/{task_id}")
    def delete_task(task_id: str, actor: str = Query(default="")):
        return _call(lambda: service.delete(task_id, actor))

    return router


def _call(operation):
    try:
        return operation()
    except LookupError as error:
        return JSONResponse(status_code=404, content={"error": {"code": "task_not_found", "message": str(error)}})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"error": {"code": "task_conflict", "message": str(error)}})
