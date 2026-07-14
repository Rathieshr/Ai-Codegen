"""Token Intelligence REST API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_token_intelligence_router(service, compiler_service=None) -> APIRouter:
    router = APIRouter(prefix="/token-intelligence", tags=["Token Intelligence"])

    @router.post("/optimize")
    def optimize(payload: dict) -> dict:
        compiled = payload.get("compiledPrompt")
        compiled_id = str(payload.get("compiledPromptId") or "")
        if not isinstance(compiled, dict) and compiled_id and compiler_service:
            compiled = compiler_service.get(compiled_id)
            if not isinstance(compiled, dict):
                raise HTTPException(status_code=404, detail="Compiled Prompt not found.")
        if not isinstance(compiled, dict):
            raise HTTPException(status_code=422, detail="compiledPrompt or compiledPromptId is required.")
        try:
            return service.optimize(
                compiled,
                budget_tokens=int(payload.get("budgetTokens") or 4096),
                reserved_output_tokens=payload.get("reservedOutputTokens"),
                actual_tokens=payload.get("actualTokens"),
                correlation_id=str(payload.get("correlationId") or ""),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{budgeted_prompt_id}")
    def get(budgeted_prompt_id: str) -> dict:
        value = service.get(budgeted_prompt_id)
        if not value:
            raise HTTPException(status_code=404, detail="Budgeted Prompt not found.")
        return value

    return router
