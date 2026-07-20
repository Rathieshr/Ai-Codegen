"""Engineering Estimation REST API."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class EstimationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    artifact: dict[str, Any] = Field(default_factory=dict)
    planningPackage: dict[str, Any] = Field(default_factory=dict)
    children: list[dict[str, Any]] = Field(default_factory=list)
    repositoryContext: dict[str, Any] = Field(default_factory=dict)
    repositoryIntelligence: dict[str, Any] = Field(default_factory=dict)
    engineeringMemory: dict[str, Any] = Field(default_factory=dict)
    memoryContext: dict[str, Any] = Field(default_factory=dict)
    dependencyAnalysis: list[Any] = Field(default_factory=list)
    architectureRules: list[Any] = Field(default_factory=list)
    technologyStack: list[Any] | str = Field(default_factory=list)
    acceptanceCriteria: list[Any] = Field(default_factory=list)
    riskAnalysis: list[Any] = Field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class RecalculateRequest(EstimationRequest):
    estimateId: str


class OverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engineeringHours: float | None = None
    engineeringDays: float | None = None
    storyPoints: float | None = None
    estimatedSprintCount: float | None = None
    developersNeeded: int | None = None
    suggestedTeamSize: int | None = None
    confidence: float | None = None
    risk: str | None = None
    complexity: str | None = None
    overrideReason: str
    actor: str = ""
    expectedEstimateId: str = ""
    expectedOverrideRevision: int | None = None


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    actualDurationHours: float
    actualStoryPoints: float | None = None
    actualCompletionDate: str = ""
    reviewCount: int = 0
    prIterations: int = 0
    reopenedWork: int = 0
    regressionIssues: int = 0


def build_engineering_estimation_router(engine) -> APIRouter:
    router = APIRouter(prefix="/planning", tags=["Engineering Estimation"])

    def correlation(value: str) -> str:
        return value or f"corr-{uuid4().hex[:16]}"

    def call(action):
        try: return action()
        except LookupError as error: return JSONResponse(status_code=404, content={"error": {"code": "estimate_not_found", "message": str(error)}})
        except ValueError as error: return JSONResponse(status_code=400, content={"error": {"code": "invalid_estimate_request", "message": str(error)}})

    @router.post("/estimate")
    def estimate(request: EstimationRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: engine.estimate(request.payload(), correlation_id=correlation(x_correlation_id)))

    @router.post("/task-estimate")
    def task_estimate(request: EstimationRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: engine.estimate_task(request.payload(), correlation_id=correlation(x_correlation_id)))

    @router.get("/estimate/{estimate_id}")
    def get_estimate(estimate_id: str): return call(lambda: engine.get(estimate_id))

    @router.get("/estimate-summary/{estimate_id}")
    def get_summary(estimate_id: str): return call(lambda: engine.summary(estimate_id))

    @router.post("/estimate/recalculate")
    def recalculate(request: RecalculateRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: engine.recalculate(request.payload(), correlation_id=correlation(x_correlation_id)))

    @router.post("/estimate/{estimate_id}/override")
    def override(estimate_id: str, request: OverrideRequest): return call(lambda: engine.override(estimate_id, request.model_dump(), actor=request.actor))

    @router.post("/estimate/{estimate_id}/approve")
    def approve(estimate_id: str, actor: str = ""): return call(lambda: engine.approve(estimate_id, actor))

    @router.post("/estimate/{estimate_id}/outcome")
    def outcome(estimate_id: str, request: OutcomeRequest): return call(lambda: engine.learn(estimate_id, request.model_dump()))

    @router.get("/{planning_id}/estimate")
    def planning_pack_estimate(planning_id: str, project_id: str = Query(default="", alias="projectId")):
        return call(lambda: engine.planning_pack(planning_id, project_id))

    @router.put("/{planning_id}/estimate")
    def override_planning_pack(planning_id: str, request: OverrideRequest, project_id: str = Query(default="", alias="projectId")):
        return call(lambda: engine.override_planning_pack(planning_id, request.model_dump(), actor=request.actor, project_id=project_id))

    return router
