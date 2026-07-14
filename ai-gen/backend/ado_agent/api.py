"""REST surface for Azure DevOps agent runs and approval packs."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .service import ActionPackApprovalError, ActionPackConflictError, ActionPackNotFoundError, ActionPackPolicyError


class ActionPackDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str
    reason: str = ""


class ActionPackApplyRequest(ActionPackDecisionRequest):
    idempotency_key: str = Field(default="", alias="idempotencyKey")


def build_ado_agent_router(service) -> APIRouter:
    router = APIRouter(prefix="/ado-agent", tags=["Azure DevOps Agent"])

    def call(action):
        try:
            return action()
        except ActionPackNotFoundError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": str(error)}})
        except ActionPackConflictError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "stale_source_revision", "message": str(error)}})
        except (ActionPackApprovalError, ActionPackPolicyError) as error:
            return JSONResponse(status_code=403, content={"error": {"code": "approval_or_policy_required", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "validation_error", "message": str(error)}})

    @router.get("/runs")
    def runs():
        return service.list_runs()

    @router.get("/runs/{run_id}")
    def run(run_id: str):
        return call(lambda: service.get_run(run_id))

    @router.get("/action-packs")
    def action_packs():
        return service.list_packs()

    @router.get("/action-packs/{pack_id}")
    def action_pack(pack_id: str):
        return call(lambda: service.get_pack(pack_id))

    @router.post("/action-packs/{pack_id}/approve")
    def approve(pack_id: str, request: ActionPackDecisionRequest):
        return call(lambda: service.approve(pack_id, request.actor, reason=request.reason))

    @router.post("/action-packs/{pack_id}/reject")
    def reject(pack_id: str, request: ActionPackDecisionRequest):
        return call(lambda: service.reject(pack_id, request.actor, reason=request.reason))

    @router.post("/action-packs/{pack_id}/apply")
    def apply(pack_id: str, request: ActionPackApplyRequest):
        return call(lambda: service.apply(pack_id, request.actor, reason=request.reason, idempotency_key=request.idempotency_key))

    return router
