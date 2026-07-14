"""Execution Center REST API."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = ""


def build_execution_center_router(service) -> APIRouter:
    router = APIRouter(prefix="/execution", tags=["Execution Center"])

    @router.get("")
    def list_executions(search: str = "", status: str = "", provider: str = "", offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250)):
        return service.list(search=search, status=status, provider=provider, offset=offset, limit=limit)

    @router.get("/{execution_id}")
    def details(execution_id: str):
        return _get(service.get, execution_id)

    @router.get("/{execution_id}/timeline")
    def timeline(execution_id: str):
        return _get(service.timeline, execution_id)

    @router.get("/{execution_id}/diagnostics")
    def diagnostics(execution_id: str):
        return _get(service.diagnostics, execution_id)

    @router.post("/{execution_id}/retry")
    def retry(execution_id: str, request: RetryRequest | None = None):
        try:
            return service.retry(execution_id, request.reason if request else "")
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "execution_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "execution_retry_unavailable", "message": str(error)}})

    return router


def _get(operation, execution_id: str):
    try:
        return operation(execution_id)
    except LookupError as error:
        return JSONResponse(status_code=404, content={"error": {"code": "execution_not_found", "message": str(error)}})
