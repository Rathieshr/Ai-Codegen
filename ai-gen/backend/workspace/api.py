"""Engineering Command Center workspace APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class WorkspacePreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    user_id: str = Field(default="", alias="userId")
    role: str = "viewer"
    theme: str | None = None
    density: str | None = None
    sidebar_collapsed: bool | None = Field(default=None, alias="sidebarCollapsed")
    default_workspace: str | None = Field(default=None, alias="defaultWorkspace")
    notifications_enabled: bool | None = Field(default=None, alias="notificationsEnabled")
    command_palette_enabled: bool | None = Field(default=None, alias="commandPaletteEnabled")


def build_workspace_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/workspace", tags=["Engineering Command Center"])

    def identity(user_id: str, header_user: str) -> str:
        return user_id or header_user or "current-user"

    @router.get("")
    def workspace(user_id: str = Query(default="", alias="userId"), role: str = Query(default="viewer"), x_hei_user: str = Header(default="", alias="X-HEI-User")):
        return service.get_workspace(identity(user_id, x_hei_user), role)

    @router.get("/preferences")
    def preferences(user_id: str = Query(default="", alias="userId"), x_hei_user: str = Header(default="", alias="X-HEI-User")):
        return service.get_preferences(identity(user_id, x_hei_user))

    @router.put("/preferences")
    def update_preferences(request: WorkspacePreferencesRequest, x_hei_user: str = Header(default="", alias="X-HEI-User")):
        payload = request.model_dump(by_alias=True, exclude_none=True)
        user_id = identity(payload.pop("userId", ""), x_hei_user)
        role = str(payload.pop("role", "viewer"))
        try:
            return service.update_preferences(user_id, payload, role)
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_workspace_preferences", "message": str(error)}})

    @router.get("/navigation")
    def navigation(role: str = Query(default="viewer")):
        return service.get_navigation(role)

    @router.post("/diagnostics")
    def diagnostics(request: dict = Body(...)):
        return service.record_diagnostic(request)

    return router
