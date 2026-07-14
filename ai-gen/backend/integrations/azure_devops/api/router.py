"""Read-only Azure DevOps integration API."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from ..domain import AzureDevOpsIntegrationError
from .contracts import (
    AzureDevOpsReconcileRequest, AzureDevOpsSyncRequest, RegisterConnectionRequest,
    WebhookRequest, WIQLRequest,
)


def build_azure_devops_router(module) -> APIRouter:
    router = APIRouter(prefix="/integrations/azure-devops", tags=["Azure DevOps Integration"])

    def correlation(value: str) -> str:
        return value or f"corr-{uuid4().hex[:16]}"

    def call(action):
        try:
            return action()
        except AzureDevOpsIntegrationError as error:
            status = error.status or {"validation_error": 400, "authentication_failed": 401, "authorization_failed": 403, "not_found": 404, "rate_limited": 429, "timeout": 504, "cancelled": 499}.get(error.code, 503)
            return JSONResponse(status_code=status, content={"error": {"code": error.code, "message": str(error), "retryable": error.retryable, "correlationId": error.correlation_id}})

    @router.post("/connections", status_code=201)
    def register_connection(request: RegisterConnectionRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.connections.register(request.as_service_input(), correlation_id=correlation(x_correlation_id)))

    @router.get("/connections")
    def list_connections():
        return {"connections": module.connections.list()}

    @router.get("/connections/{connection_id}")
    def get_connection(connection_id: str):
        return call(lambda: module.connections.get(connection_id) or module.connections.require(connection_id))

    @router.post("/connections/{connection_id}/validate")
    def validate_connection(connection_id: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.connections.validate(connection_id, correlation_id=correlation(x_correlation_id)))

    @router.get("/connections/{connection_id}/health")
    def connection_health(connection_id: str):
        return call(lambda: module.connections.health(connection_id))

    @router.get("/connections/{connection_id}/organizations")
    def list_organizations(connection_id: str):
        return call(lambda: module.projects.list_organizations(connection_id))

    @router.get("/connections/{connection_id}/projects")
    def list_projects(connection_id: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"projects": module.projects.list_projects(connection_id, correlation_id=correlation(x_correlation_id))})

    @router.get("/connections/{connection_id}/projects/{project_id}")
    def get_project(connection_id: str, project_id: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.projects.get_project(connection_id, project_id, correlation_id=correlation(x_correlation_id)))

    @router.get("/connections/{connection_id}/projects/{project_id}/teams")
    def list_teams(connection_id: str, project_id: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"teams": module.projects.list_teams(connection_id, project_id, correlation_id=correlation(x_correlation_id))})

    @router.get("/connections/{connection_id}/projects/{project}/iterations")
    def list_iterations(connection_id: str, project: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"iterations": module.iterations.list_iterations(connection_id, project, correlation_id=correlation(x_correlation_id))})

    @router.get("/connections/{connection_id}/projects/{project}/iterations/current")
    def current_sprint(connection_id: str, project: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.iterations.get_current_sprint(connection_id, project, correlation_id=correlation(x_correlation_id)) or {"status": "NoCurrentSprint"})

    @router.post("/connections/{connection_id}/work-items/query")
    def query_work_items(connection_id: str, request: WIQLRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"workItems": module.work_items.query(connection_id, request.project, request.query, correlation_id=correlation(x_correlation_id))})

    @router.get("/connections/{connection_id}/projects/{project}/work-items/{work_item_id}/hierarchy")
    def work_item_hierarchy(connection_id: str, project: str, work_item_id: int, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.work_items.get_hierarchy(connection_id, project, work_item_id, correlation_id=correlation(x_correlation_id)))

    @router.get("/connections/{connection_id}/projects/{project}/work-items/{work_item_id}/revisions")
    def work_item_revisions(connection_id: str, project: str, work_item_id: int, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"revisions": module.work_items.get_revisions(connection_id, project, work_item_id, correlation_id=correlation(x_correlation_id))})

    @router.get("/connections/{connection_id}/projects/{project}/repositories")
    def list_repositories(connection_id: str, project: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"repositories": module.repositories.list_repositories(connection_id, project, correlation_id=correlation(x_correlation_id))})

    @router.get("/connections/{connection_id}/projects/{project}/repositories/{repository_id}")
    def get_repository(connection_id: str, project: str, repository_id: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.repositories.get_repository(connection_id, project, repository_id, correlation_id=correlation(x_correlation_id)))

    @router.get("/connections/{connection_id}/projects/{project}/pull-requests")
    def list_pull_requests(connection_id: str, project: str, repository_id: str = Query(default="", alias="repositoryId"), x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"pullRequests": module.pull_requests.list_pull_requests(connection_id, project, repository_id, correlation_id=correlation(x_correlation_id))})

    @router.get("/connections/{connection_id}/projects/{project}/repositories/{repository_id}/pull-requests/{pull_request_id}")
    def get_pull_request(connection_id: str, project: str, repository_id: str, pull_request_id: int, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.pull_requests.get_pull_request(connection_id, project, repository_id, pull_request_id, correlation_id=correlation(x_correlation_id)))

    @router.get("/connections/{connection_id}/projects/{project}/builds")
    def list_builds(connection_id: str, project: str, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: {"builds": module.pull_requests.list_builds(connection_id, project, correlation_id=correlation(x_correlation_id))})

    @router.post("/connections/{connection_id}/webhooks")
    def receive_webhook(connection_id: str, request: WebhookRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.webhooks.handle(connection_id, request.as_payload(), correlation_id=correlation(x_correlation_id)))

    @router.post("/projects/{project_id}/sync", status_code=202)
    def synchronize_project(project_id: str, request: AzureDevOpsSyncRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.sync.request_sync(request.connection_id, project_id, request.sync_type, correlation_id=correlation(x_correlation_id)))

    @router.get("/projects/{project_id}/sync-status")
    def project_sync_status(project_id: str):
        return module.sync.status(project_id)

    @router.get("/projects/{project_id}/sync-history")
    def project_sync_history(project_id: str, limit: int = Query(default=50, ge=1, le=200)):
        return module.sync.history(project_id, limit)

    @router.post("/webhooks", status_code=202)
    def synchronize_webhook(request: WebhookRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.sync.receive_webhook(request.as_payload(), correlation_id=correlation(x_correlation_id)))

    @router.post("/projects/{project_id}/reconcile", status_code=202)
    def reconcile_project(project_id: str, request: AzureDevOpsReconcileRequest, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: module.sync.request_reconciliation(request.connection_id, project_id, correlation_id=correlation(x_correlation_id)))

    return router
