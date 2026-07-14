"""HTTP API for Engineering Memory candidate generation and review."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query


def build_memory_candidate_router(service) -> APIRouter:
    router = APIRouter(prefix="/memory-candidates", tags=["Engineering Memory Candidates"])

    @router.post("/generate")
    def generate(payload: dict) -> dict:
        try:
            return service.generate(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("")
    def list_candidates(project_id: str = Query(default="")) -> dict:
        return service.list(project_id)

    @router.get("/{candidate_id}")
    def get(candidate_id: str) -> dict:
        candidate = service.get(candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Engineering Memory candidate not found.")
        return candidate

    @router.post("/{candidate_id}/approve")
    def approve(candidate_id: str, payload: dict | None = None) -> dict:
        try:
            return service.approve(candidate_id, str((payload or {}).get("actor") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/{candidate_id}/reject")
    def reject(candidate_id: str, payload: dict | None = None) -> dict:
        try:
            value = payload or {}
            return service.reject(candidate_id, str(value.get("actor") or ""), str(value.get("reason") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
