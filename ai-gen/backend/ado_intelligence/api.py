"""REST API for read-only ADO work-item intelligence recommendations."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.integrations.azure_devops.domain import AzureDevOpsIntegrationError

from .service import RecommendationNotFoundError, StaleRecommendationError, WorkItemNotFoundError


class AnalyzeWorkItemRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    project_id: str = Field(default="", alias="projectId")
    repository_id: str = Field(default="", alias="repositoryId")
    manual_requirement: dict[str, Any] | None = Field(default=None, alias="manualRequirement")
    imported_requirement: dict[str, Any] | None = Field(default=None, alias="importedRequirement")
    knowledge_registry: dict[str, Any] | None = Field(default=None, alias="knowledgeRegistry")
    token_budget: int = Field(default=1200, alias="tokenBudget", ge=300, le=32000)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = ""


class EstimateWorkItemRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    action: str = "generate"
    project_id: str = Field(default="", alias="projectId")
    team_id: str = Field(default="", alias="teamId")
    estimate_id: str = Field(default="", alias="estimateId")
    actor: str = ""
    story_points: int | None = Field(default=None, alias="storyPoints")
    edit_reason: str = Field(default="", alias="editReason")


class PullRequestAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    project_id: str = Field(default="", alias="projectId")
    connection_id: str = Field(default="", alias="connectionId")
    repository_id: str = Field(default="", alias="repositoryId")


class PullRequestCommentRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    project_id: str = Field(default="", alias="projectId")
    connection_id: str = Field(default="", alias="connectionId")
    repository_id: str = Field(default="", alias="repositoryId")
    comment_preview_id: str = Field(default="", alias="commentPreviewId")
    approved: bool = False
    approved_by: str = Field(default="", alias="approvedBy")
    idempotency_key: str = Field(default="", alias="idempotencyKey")
    reason: str = ""


def build_ado_intelligence_router(service) -> APIRouter:
    router = APIRouter(prefix="/ado-intelligence", tags=["ADO Work Item Intelligence"])

    def correlation(value: str) -> str:
        return value or f"corr-{uuid4().hex[:16]}"

    def call(action):
        try:
            return action()
        except (WorkItemNotFoundError, RecommendationNotFoundError) as error:
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": str(error)}})
        except StaleRecommendationError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "stale_recommendation", "message": f"Recommendation {error} is stale. Regenerate it from the current work-item revision."}})
        except PermissionError as error:
            return JSONResponse(status_code=403, content={"error": {"code": "approval_or_permission_required", "message": str(error)}})
        except AzureDevOpsIntegrationError as error:
            return JSONResponse(status_code=error.status or (503 if error.retryable else 400), content={"error": {"code": error.code, "message": str(error), "retryable": error.retryable, "correlationId": error.correlation_id}})
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "validation_error", "message": str(error)}})

    @router.post("/work-items/{work_item_id}/analyze")
    def analyze(work_item_id: str, request: AnalyzeWorkItemRequest | None = None, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        payload = request.model_dump(by_alias=True, exclude_none=True) if request else {}
        return call(lambda: service.analyze(work_item_id, payload, correlation_id=correlation(x_correlation_id)))

    @router.get("/work-items/{work_item_id}/recommendations")
    def recommendations(work_item_id: str, project_id: str = Query(default="", alias="projectId")):
        return service.list_recommendations(work_item_id, project_id)

    @router.post("/recommendations/{recommendation_id}/approve")
    def approve(recommendation_id: str, request: DecisionRequest | None = None):
        return call(lambda: service.approve(recommendation_id, request.actor if request else ""))

    @router.post("/recommendations/{recommendation_id}/reject")
    def reject(recommendation_id: str, request: DecisionRequest | None = None):
        return call(lambda: service.reject(recommendation_id, request.actor if request else ""))

    @router.post("/recommendations/{recommendation_id}/regenerate")
    def regenerate(recommendation_id: str, request: AnalyzeWorkItemRequest | None = None, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        payload = request.model_dump(by_alias=True, exclude_none=True) if request else {}
        return call(lambda: service.regenerate(recommendation_id, payload, correlation_id=correlation(x_correlation_id)))

    @router.post("/work-items/{work_item_id}/estimate")
    def estimate(work_item_id: str, request: EstimateWorkItemRequest | None = None, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        payload = request.model_dump(by_alias=True, exclude_none=True) if request else {}
        return call(lambda: service.estimation.handle(work_item_id, payload, correlation_id=correlation(x_correlation_id)))

    @router.get("/work-items/{work_item_id}/estimate")
    def get_estimate(work_item_id: str, project_id: str = Query(default="", alias="projectId")):
        return call(lambda: service.estimation.get(work_item_id, project_id))

    @router.get("/projects/{project_id}/estimation-accuracy")
    def estimation_accuracy(project_id: str, team_id: str = Query(default="", alias="teamId")):
        return service.estimation.accuracy(project_id, team_id)

    @router.post("/pull-requests/{pull_request_id}/analyze")
    def analyze_pull_request(pull_request_id: str, request: PullRequestAnalysisRequest | None = None, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        payload = request.model_dump(by_alias=True, exclude_none=True) if request else {}
        return call(lambda: service.pull_requests.analyze(pull_request_id, payload, correlation_id=correlation(x_correlation_id)))

    @router.get("/pull-requests/{pull_request_id}/report")
    def pull_request_report(pull_request_id: str, project_id: str = Query(default="", alias="projectId")):
        return call(lambda: service.pull_requests.get(pull_request_id, project_id))

    @router.post("/pull-requests/{pull_request_id}/comment-preview")
    def preview_pull_request_comment(pull_request_id: str, request: PullRequestCommentRequest | None = None):
        payload = request.model_dump(by_alias=True, exclude_none=True) if request else {}
        return call(lambda: service.pull_requests.preview_comment(pull_request_id, payload))

    @router.post("/pull-requests/{pull_request_id}/post-approved-comment")
    def post_approved_pull_request_comment(pull_request_id: str, request: PullRequestCommentRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        payload = request.model_dump(by_alias=True, exclude_none=True)
        return call(lambda: service.pull_requests.post_approved_comment(pull_request_id, payload, correlation_id=correlation(x_correlation_id)))

    @router.post("/pull-requests/{pull_request_id}/reanalyze")
    def reanalyze_pull_request(pull_request_id: str, request: PullRequestAnalysisRequest | None = None, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        payload = request.model_dump(by_alias=True, exclude_none=True) if request else {}
        payload["reanalyze"] = True
        return call(lambda: service.pull_requests.analyze(pull_request_id, payload, correlation_id=correlation(x_correlation_id)))

    @router.get("/projects/{project_id}/sprints/current")
    def current_sprint(project_id: str, team_id: str = Query(default="", alias="teamId")):
        return call(lambda: service.sprints.current(project_id, team_id))

    @router.get("/projects/{project_id}/sprints/{iteration_id}/report")
    def sprint_report(project_id: str, iteration_id: str, team_id: str = Query(default="", alias="teamId")):
        return call(lambda: service.sprints.report(project_id, iteration_id, team_id=team_id))

    @router.get("/projects/{project_id}/sprints/{iteration_id}/burndown")
    def sprint_burndown(project_id: str, iteration_id: str, team_id: str = Query(default="", alias="teamId")):
        return call(lambda: service.sprints.burndown(project_id, iteration_id, team_id=team_id))

    @router.get("/projects/{project_id}/sprints/{iteration_id}/risks")
    def sprint_risks(project_id: str, iteration_id: str, team_id: str = Query(default="", alias="teamId")):
        return call(lambda: service.sprints.risks(project_id, iteration_id, team_id=team_id))

    return router
