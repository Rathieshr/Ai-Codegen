"""Command Center production health APIs."""

from __future__ import annotations

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse


def build_command_center_hardening_router(service) -> APIRouter:
    router = APIRouter(prefix="/command-center", tags=["Engineering Command Center"])

    @router.get("/health")
    def health(force: bool = False):
        return service.snapshot(force=force, include_diagnostics=False)

    @router.get("/performance")
    def performance(force: bool = False):
        value = service.snapshot(force=force, include_diagnostics=False)
        return {"performance": value["performance"], "cache": value["cache"], "generatedAt": value["generatedAt"]}

    @router.get("/diagnostics")
    def diagnostics(
        force: bool = False,
        role: str = Query(default="viewer"),
        x_hei_role: str = Header(default="", alias="X-HEI-Role"),
    ):
        if str(x_hei_role or role).strip().casefold() != "admin":
            return JSONResponse(status_code=403, content={"error": {"code": "diagnostics_forbidden", "message": "Command Center diagnostics require AI Gen Admin access."}})
        return service.snapshot(force=force, include_diagnostics=True)

    return router
