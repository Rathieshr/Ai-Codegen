"""Execution Runtime hardening report APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_runtime_hardening_router(harness) -> APIRouter:
    router = APIRouter(prefix="/runtime/hardening", tags=["Runtime Hardening"])

    @router.post("/run")
    def run() -> dict:
        return harness.run()

    @router.get("/report")
    def report() -> dict:
        value = harness.latest()
        if value is None:
            raise HTTPException(status_code=404, detail="No Runtime Hardening benchmark report is available.")
        return value

    @router.get("/runs/{run_id}")
    def get(run_id: str) -> dict:
        value = harness.get(run_id)
        if value is None:
            raise HTTPException(status_code=404, detail="Runtime Hardening run not found.")
        return value

    return router
