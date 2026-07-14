"""Approval Center REST API."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .service import ApprovalConflictError, ApprovalNotFoundError, ApprovalPermissionError


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str
    role: str
    reason: str = ""


def build_approval_center_router(service) -> APIRouter:
    router = APIRouter(prefix="/approvals", tags=["Approval Center"])

    @router.get("")
    def approvals(category: str = "", status: str = "", search: str = "", offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250)):
        return service.list(category=category, status=status, search=search, offset=offset, limit=limit)

    @router.get("/{approval_id}")
    def details(approval_id: str):
        return _get(lambda: service.get(approval_id))

    @router.post("/{approval_id}/approve")
    def approve(approval_id: str, request: ApprovalDecisionRequest):
        return _get(lambda: service.approve(approval_id, request.actor, request.role, request.reason))

    @router.post("/{approval_id}/reject")
    def reject(approval_id: str, request: ApprovalDecisionRequest):
        return _get(lambda: service.reject(approval_id, request.actor, request.role, request.reason))

    return router


def _get(operation):
    try:
        return operation()
    except ApprovalNotFoundError as error:
        return JSONResponse(status_code=404, content={"error": {"code": "approval_not_found", "message": str(error)}})
    except ApprovalPermissionError as error:
        return JSONResponse(status_code=403, content={"error": {"code": "approval_permission_denied", "message": str(error)}})
    except (ApprovalConflictError, ValueError, RuntimeError) as error:
        return JSONResponse(status_code=409, content={"error": {"code": "approval_conflict", "message": str(error)}})
