"""Consumer convergence endpoints."""

from fastapi import APIRouter, HTTPException

from .contracts import ConsumerRequest


def build_convergence_router(package_service, consumer_service) -> APIRouter:
    router = APIRouter(prefix="/execution-packages", tags=["Platform Convergence"])

    @router.post("/{package_id}/consume/{consumer}")
    def consume(package_id: str, consumer: str, payload: dict | None = None) -> dict:
        package = package_service.get(package_id)
        if not package: raise HTTPException(status_code=404, detail="Execution package not found.")
        value = payload or {}
        try: return consumer_service.consume(ConsumerRequest(consumer=consumer, execution_package=package, agent_context=dict(value.get("agentContext") or {}), execution_mode=str(value.get("executionMode") or "Implement"), runtime_evidence=dict(value.get("runtimeEvidence") or {}), correlation_id=str(value.get("correlationId") or "")))
        except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
