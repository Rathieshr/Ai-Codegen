"""HTTP API for QA Trigger planning."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_qa_trigger_router(service) -> APIRouter:
    router = APIRouter(prefix="/qa-trigger", tags=["QA Trigger"])

    @router.post("/evaluate")
    def evaluate(payload: dict) -> dict:
        try:
            return service.evaluate(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{plan_id}")
    def get(plan_id: str) -> dict:
        value = service.get(plan_id)
        if not value:
            raise HTTPException(status_code=404, detail="QA Execution Plan not found.")
        return value

    return router
