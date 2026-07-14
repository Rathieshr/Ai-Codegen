"""Prompt Intelligence hardening and benchmark APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_prompt_intelligence_hardening_router(harness) -> APIRouter:
    router = APIRouter(prefix="/prompt-intelligence/hardening", tags=["Prompt Intelligence Hardening"])

    @router.post("/run")
    def run() -> dict:
        return harness.run()

    @router.get("/report")
    def report() -> dict:
        value = harness.latest()
        if not value:
            raise HTTPException(status_code=404, detail="No Prompt Intelligence benchmark report is available.")
        return value

    @router.get("/runs/{run_id}")
    def get(run_id: str) -> dict:
        value = harness.get(run_id)
        if not value:
            raise HTTPException(status_code=404, detail="Prompt Intelligence hardening run not found.")
        return value

    return router
