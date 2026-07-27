"""Engineering Review REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse


def build_engineering_review_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/engineering-reviews", tags=["Engineering Review"])

    def call(action):
        try:
            return action()
        except LookupError as error:
            return JSONResponse(status_code=404, content={"error": {"code": "engineering_review_not_found", "message": str(error)}})
        except PermissionError as error:
            return JSONResponse(status_code=403, content={"error": {"code": "engineering_review_permission_denied", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=409, content={"error": {"code": "engineering_review_conflict", "message": str(error)}})

    @router.post("")
    def create(request: dict[str, Any] = Body(...)):
        return call(lambda: service.create(request))

    @router.get("")
    def list_reviews(status: str = "", reviewer: str = "", search: str = ""):
        return call(lambda: service.list(status=status, reviewer=reviewer, search=search))

    @router.get("/proposal/{proposal_id}")
    def for_proposal(proposal_id: str):
        return call(lambda: service.for_proposal(proposal_id))

    @router.get("/{review_id}")
    def get(review_id: str):
        return call(lambda: service.get(review_id))

    @router.post("/{review_id}/assign")
    def assign(review_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.assign(review_id, request))

    @router.post("/{review_id}/comments")
    def comment(review_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.comment(review_id, request))

    @router.post("/{review_id}/comments/{comment_id}/resolve")
    def resolve_comment(review_id: str, comment_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.resolve_comment(review_id, comment_id, request))

    @router.post("/{review_id}/change-requests")
    def request_change(review_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.request_change(review_id, request))

    @router.post("/{review_id}/change-requests/{change_id}/resolve")
    def resolve_change(review_id: str, change_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.resolve_change(review_id, change_id, request))

    @router.post("/{review_id}/decision")
    def decide(review_id: str, request: dict[str, Any] = Body(...)):
        return call(lambda: service.decide(review_id, request))

    @router.get("/{review_id}/history")
    def history(review_id: str, search: str = ""):
        return call(lambda: service.history(review_id, search=search))

    @router.get("/{review_id}/report")
    def report(
        review_id: str,
        report_type: str = Query(default="Review Report", alias="type"),
        output_format: str = Query(default="Markdown", alias="format"),
    ):
        return call(lambda: service.report(review_id, report_type, output_format))

    @router.get("/proposal/{proposal_id}/synchronization-authorization")
    def authorize_synchronization(proposal_id: str):
        return call(lambda: service.authorize_synchronization(proposal_id))

    return router
