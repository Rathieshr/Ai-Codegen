"""HTTP API for Pull Request candidate generation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_pr_candidate_router(service) -> APIRouter:
    router = APIRouter(prefix="/pr-candidates", tags=["Pull Request Candidates"])

    @router.post("/generate")
    def generate(payload: dict) -> dict:
        try:
            return service.generate(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("")
    def list_candidates() -> dict:
        return service.list()

    @router.get("/{candidate_id}")
    def get(candidate_id: str) -> dict:
        candidate = service.get(candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Pull Request candidate not found.")
        return candidate

    return router
