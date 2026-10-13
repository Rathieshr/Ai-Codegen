"""REST endpoints for Phase 6.10 operational validation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .safety import LiveTestSafetyError


class OperationalValidationRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    mode: str = "Live"
    project_id: str = Field(default="", alias="projectId")
    connection_id: str = Field(default="", alias="connectionId")
    project_confirmation: str = Field(default="", alias="projectConfirmation")
    allow_writes: bool = Field(default=False, alias="allowWrites")


def build_ado_operational_router(validator: Any) -> APIRouter:
    router = APIRouter(prefix="/ado-operational-validation", tags=["Azure DevOps Operational Validation"])

    @router.post("/run")
    def run(request: OperationalValidationRequest):
        try:
            return validator.run(request.model_dump(by_alias=True, exclude_none=True))
        except LiveTestSafetyError as error:
            return JSONResponse(status_code=403, content={"error": {"code": "live_test_safety_block", "message": str(error)}})

    @router.get("/report")
    def report():
        value = validator.latest()
        if not value: raise HTTPException(status_code=404, detail="No Phase 6.10 operational validation report is available.")
        return value

    @router.get("/readiness")
    def readiness():
        return validator.readiness()

    @router.get("/traces/{correlation_id}")
    def trace(correlation_id: str):
        value = validator.trace(correlation_id)
        if not value: raise HTTPException(status_code=404, detail="Operational correlation trace not found.")
        return value

    return router
