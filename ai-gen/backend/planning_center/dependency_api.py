"""Planning dependency REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse


def build_planning_dependency_router(service) -> APIRouter:
    router = APIRouter(tags=["Planning Dependencies"])

    @router.get("/planning/{planning_id}/dependencies")
    def get_dependencies(planning_id: str, project_id: str = Query(default="", alias="projectId")):
        return _call(lambda: service.get(planning_id, project_id))

    @router.put("/dependency")
    def put_dependency(request: dict[str, Any] = Body(...), actor: str = Query(default="")):
        return _call(lambda: service.put(request, actor or str(request.get("actor") or "")))

    @router.delete("/dependency")
    def delete_dependency(request: dict[str, Any] = Body(...), actor: str = Query(default="")):
        dependency_id = str(request.get("dependencyId") or "").strip()
        if not dependency_id:
            return JSONResponse(status_code=422, content={"error": {"code": "dependency_id_required", "message": "dependencyId is required."}})
        return _call(lambda: service.delete(dependency_id, actor or str(request.get("actor") or "")))

    return router


def _call(operation):
    try:
        return operation()
    except LookupError as error:
        return JSONResponse(status_code=404, content={"error": {"code": "dependency_not_found", "message": str(error)}})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"error": {"code": "dependency_conflict", "message": str(error)}})
