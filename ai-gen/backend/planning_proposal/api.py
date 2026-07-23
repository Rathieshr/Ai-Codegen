"""Planning Proposal Engine REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse


def build_planning_proposal_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/planning/proposal", tags=["Planning Proposal Engine"])

    def call(action: Any):
        try:
            return action()
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "planning_proposal_not_found", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_planning_proposal", "message": str(error)}})

    @router.post("")
    def build(request: dict[str, Any] = Body(...)):
        return call(lambda: service.build(request))

    @router.get("/history")
    def history(proposal_id: str = Query(..., alias="proposalId")):
        return call(lambda: service.history(proposal_id))

    @router.post("/regenerate")
    def regenerate(request: dict[str, Any] = Body(...)):
        return call(lambda: service.regenerate(request))

    @router.post("/validate")
    def validate(request: dict[str, Any] = Body(...)):
        return call(lambda: service.validate(request))

    @router.post("/review")
    def review(request: dict[str, Any] = Body(...)):
        return call(lambda: service.review(request))

    @router.post("/approve")
    def approve(request: dict[str, Any] = Body(...)):
        return call(lambda: service.approve(request))

    @router.get("/{proposal_id}")
    def get(proposal_id: str):
        return call(lambda: service.get(proposal_id))

    @router.put("/{proposal_id}")
    def update(proposal_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.update(proposal_id, request))

    return router
