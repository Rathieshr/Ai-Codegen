"""Shared Engineering Intelligence API for all HEI entry surfaces."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .shared_orchestrator import EngineeringContextNotFoundError


class EngineeringContextRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    entry_mode: str = Field(default="REQUIREMENT", alias="entryMode")
    project_id: str = Field(default="", alias="projectId")
    project_name: str = Field(default="", alias="projectName")
    repository_id: str = Field(default="", alias="repositoryId")
    work_item_id: str = Field(default="", alias="workItemId")
    planning_proposal_id: str = Field(default="", alias="planningProposalId")
    requirement: dict[str, Any] = Field(default_factory=dict)
    analyze_work_item: bool = Field(default=True, alias="analyzeWorkItem")


class AcceptanceCriteriaRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    requirement: dict[str, Any]
    project_profile: dict[str, Any] = Field(default_factory=dict, alias="projectProfile")
    options: dict[str, Any] = Field(default_factory=dict)


def build_engineering_intelligence_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/engineering-intelligence", tags=["Engineering Intelligence"])

    def execute(action):
        try:
            return action()
        except EngineeringContextNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "message": str(error)}},
            )
        except ValueError as error:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "validation_error", "message": str(error)}},
            )

    def payload(request: BaseModel, correlation_id: str) -> dict[str, Any]:
        value = request.model_dump(by_alias=True, exclude_none=True)
        value["correlationId"] = correlation_id or f"corr-{uuid4().hex[:16]}"
        return value

    @router.post("/context")
    def build_context(request: EngineeringContextRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return execute(lambda: service.build_context(payload(request, x_correlation_id)))

    @router.get("/contexts/{context_id}")
    def get_context(context_id: str):
        return execute(lambda: service.get_context(context_id))

    @router.post("/work-items/{work_item_id}/analyze")
    def analyze_work_item(work_item_id: str, request: EngineeringContextRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return execute(lambda: service.analyze_work_item(work_item_id, payload(request, x_correlation_id)))

    @router.post("/acceptance-criteria/generate")
    def generate_acceptance_criteria(request: AcceptanceCriteriaRequest):
        return execute(lambda: service.generate_acceptance_criteria(request.model_dump(by_alias=True, exclude_none=True)))

    return router
