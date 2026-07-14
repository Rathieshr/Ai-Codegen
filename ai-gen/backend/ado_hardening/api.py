"""Azure DevOps Phase 6 hardening report APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .safety import LiveTestSafetyError


class AzureDevOpsHardeningRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    mode: str = "Live"
    project_id: str = Field(default="", alias="projectId")
    connection_id: str = Field(default="", alias="connectionId")
    project_confirmation: str = Field(default="", alias="projectConfirmation")
    allow_writes: bool = Field(default=False, alias="allowWrites")


def build_ado_hardening_router(harness) -> APIRouter:
    router = APIRouter(prefix="/ado-hardening", tags=["Azure DevOps Hardening"])

    @router.post("/run")
    def run(request: AzureDevOpsHardeningRequest) -> dict[str, Any]:
        try:
            return harness.run(request.model_dump(by_alias=True, exclude_none=True))
        except LiveTestSafetyError as error:
            return JSONResponse(status_code=403, content={"error": {"code": "live_test_safety_block", "message": str(error)}})

    @router.get("/report")
    def report() -> dict[str, Any]:
        value = harness.latest()
        if not value:
            raise HTTPException(status_code=404, detail="No Azure DevOps hardening report is available.")
        return value

    @router.get("/runs")
    def runs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        values = harness.list(limit)
        return {"runs": values, "count": len(values)}

    @router.get("/runs/{run_id}")
    def get(run_id: str) -> dict[str, Any]:
        value = harness.get(run_id)
        if not value:
            raise HTTPException(status_code=404, detail="Azure DevOps hardening run not found.")
        return value

    @router.get("/readiness")
    def readiness() -> dict[str, Any]:
        return harness.readiness()

    return router
