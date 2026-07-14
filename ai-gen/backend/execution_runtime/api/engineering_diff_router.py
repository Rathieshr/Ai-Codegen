"""HTTP API for semantic Engineering Diff construction and retrieval."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_engineering_diff_router(service) -> APIRouter:
    router = APIRouter(tags=["Engineering Diff"])

    @router.post("/engineering-diff")
    def build(payload: dict) -> dict:
        try:
            return service.build(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/engineering-diff/{diff_id}")
    def get(diff_id: str) -> dict:
        value = service.get(diff_id)
        if not value:
            raise HTTPException(status_code=404, detail="Engineering Diff not found.")
        return value

    return router
