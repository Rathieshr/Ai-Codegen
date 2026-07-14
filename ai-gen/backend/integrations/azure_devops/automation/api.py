"""Restricted REST surface for approved Azure DevOps automation."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..domain import AzureDevOpsIntegrationError
from .service import (
    AutomationApprovalError, AutomationConflictError, AutomationNotFoundError,
    AutomationPermissionError, AutomationValidationError,
)


class AutomationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    connection_id: str = Field(alias="connectionId")
    project_id: str = Field(default="", alias="projectId")
    idempotency_key: str = Field(default="", alias="idempotencyKey")
    executor: str = ""
    reason: str = ""


def build_ado_automation_router(service) -> APIRouter:
    router = APIRouter(prefix="/ado-automation", tags=["Approved Azure DevOps Automation"])

    def correlation(value: str) -> str:
        return value or f"corr-{uuid4().hex[:16]}"

    def call(action):
        try:
            return action()
        except AutomationNotFoundError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": str(error)}})
        except (AutomationApprovalError, AutomationPermissionError) as error:
            return JSONResponse(status_code=403, content={"error": {"code": "approval_or_permission_required", "message": str(error)}})
        except AutomationConflictError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "stale_revision", "message": str(error)}})
        except AutomationValidationError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "validation_error", "message": str(error)}})
        except AzureDevOpsIntegrationError as error:
            status = error.status or 503
            return JSONResponse(status_code=status, content={"error": {"code": error.code, "message": str(error), "retryable": error.retryable, "correlationId": error.correlation_id}})

    def payload(request: AutomationRequest) -> dict:
        return request.model_dump(by_alias=True)

    @router.post("/planning-packs/{planning_pack_id}/preview")
    def preview_planning_pack(planning_pack_id: str, request: AutomationRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: service.preview_planning_pack(planning_pack_id, payload(request), correlation_id=correlation(x_correlation_id)))

    @router.post("/planning-packs/{planning_pack_id}/apply")
    def apply_planning_pack(planning_pack_id: str, request: AutomationRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: service.apply_planning_pack(planning_pack_id, payload(request), correlation_id=correlation(x_correlation_id)))

    @router.post("/recommendations/{recommendation_id}/preview")
    def preview_recommendation(recommendation_id: str, request: AutomationRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: service.preview_recommendation(recommendation_id, payload(request), correlation_id=correlation(x_correlation_id)))

    @router.post("/recommendations/{recommendation_id}/apply")
    def apply_recommendation(recommendation_id: str, request: AutomationRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: service.apply_recommendation(recommendation_id, payload(request), correlation_id=correlation(x_correlation_id)))

    return router
