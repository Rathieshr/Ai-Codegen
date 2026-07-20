"""Azure DevOps work-item import APIs for Requirement Intelligence."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse

from backend.integrations.azure_devops.domain import AzureDevOpsIntegrationError

from .service import AzureDevOpsWorkItemImportService, ImportedWorkItemNotFoundError, UnsupportedWorkItemError


def build_ado_work_item_import_router(service: AzureDevOpsWorkItemImportService) -> APIRouter:
    router = APIRouter(prefix="/ado/workitem", tags=["HEI ADO Requirement Import"])

    def correlation(value: str) -> str:
        return value or f"corr-{uuid4().hex[:16]}"

    def call(action):
        try:
            return action()
        except ImportedWorkItemNotFoundError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "work_item_not_found", "message": str(error)}})
        except UnsupportedWorkItemError as error:
            return JSONResponse(status_code=422, content={"error": {"code": "unsupported_work_item_type", "message": str(error)}})
        except AzureDevOpsIntegrationError as error:
            return JSONResponse(status_code=error.status or 503, content={"error": {"code": error.code, "message": str(error), "retryable": error.retryable}})
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_work_item_import", "message": str(error)}})

    @router.get("/{work_item_id}")
    def get_work_item(work_item_id: str, project_id: str = Query(default="", alias="projectId"), connection_id: str = Query(default="", alias="connectionId"), refresh: bool = False, x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: service.get(work_item_id, project_id=project_id, connection_id=connection_id, refresh=refresh, correlation_id=correlation(x_correlation_id)))

    @router.post("/{work_item_id}/analyze")
    def analyze_work_item(work_item_id: str, request: dict[str, Any] | None = Body(default=None), x_correlation_id: str = Header(default="", alias="X-Correlation-ID")):
        return call(lambda: service.analyze(work_item_id, request, correlation_id=correlation(x_correlation_id)))

    return router
