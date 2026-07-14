"""HTTP API for Validation Trigger decisions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_validation_trigger_router(service) -> APIRouter:
    router = APIRouter(prefix="/validation-trigger", tags=["Validation Trigger"])

    @router.post("/evaluate")
    def evaluate(payload: dict) -> dict:
        try:
            return service.evaluate(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{decision_id}")
    def get(decision_id: str) -> dict:
        value = service.get(decision_id)
        if not value:
            raise HTTPException(status_code=404, detail="Validation Trigger decision not found.")
        return value

    return router
