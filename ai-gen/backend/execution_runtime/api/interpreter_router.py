"""HTTP API for standalone AI response interpretation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_response_interpreter_router(service) -> APIRouter:
    router = APIRouter(prefix="/runtime/interpreter", tags=["AI Response Interpreter"])

    @router.post("/interpret")
    def interpret(payload: dict) -> dict:
        try:
            return service.interpret(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Execution session not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{session_id}")
    def get(session_id: str) -> dict:
        value = service.get(session_id)
        if not value:
            raise HTTPException(status_code=404, detail="Response interpretation not found.")
        return value

    return router
