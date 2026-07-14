"""Backend-only trace and regression dashboard APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .harness import HEIEndToEndHarness


class RegressionRunRequest(BaseModel):
    scenario_id: str = Field(default="", alias="scenarioId")
    repository_mode: str = Field(default="KnowledgeSnapshot", alias="repositoryMode")
    token_budget: int = Field(default=4000, alias="tokenBudget", ge=1200, le=16000)
    failure_stage: str = Field(default="", alias="failureStage")
    repository_freshness: str = Field(default="Fresh", alias="repositoryFreshness")

    class Config:
        populate_by_name = True


def build_platform_hardening_router(harness: HEIEndToEndHarness) -> APIRouter:
    router = APIRouter(prefix="/platform", tags=["Platform Hardening"])

    @router.post("/regression/run")
    def run_regression(request: RegressionRunRequest) -> dict[str, Any]:
        try:
            if request.scenario_id:
                return harness.run_scenario(request.scenario_id, repository_mode=request.repository_mode, token_budget=request.token_budget, failure_stage=request.failure_stage, repository_freshness=request.repository_freshness)
            return harness.run_all(repository_mode=request.repository_mode, token_budget=request.token_budget, repository_freshness=request.repository_freshness)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.get("/runs/{correlation_id}/trace")
    def get_run_trace(correlation_id: str) -> dict[str, Any]:
        trace = harness.store.trace(correlation_id)
        if not trace:
            return JSONResponse(status_code=404, content={"error": f"No platform trace was found for correlation ID '{correlation_id}'."})
        run_id = trace[0].get("runId")
        return {"correlationId": correlation_id, "runId": run_id, "eventCount": len(trace), "trace": trace}

    @router.get("/regression/summary")
    def regression_summary() -> dict[str, Any]:
        return harness.summary()

    @router.get("/regression/runs")
    def regression_runs(limit: int = 100) -> dict[str, Any]:
        runs = harness.store.list_runs(limit=limit)
        return {"runs": runs, "count": len(runs)}

    @router.get("/regression/runs/{run_id}")
    def regression_run(run_id: str) -> dict[str, Any]:
        run = harness.store.get_run(run_id)
        if not run:
            return JSONResponse(status_code=404, content={"error": f"Regression run '{run_id}' was not found."})
        return run

    return router
