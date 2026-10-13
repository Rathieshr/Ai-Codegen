"""Prompt Compiler REST API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_prompt_compiler_router(service, manifest_service=None) -> APIRouter:
    router = APIRouter(prefix="/prompt-compiler", tags=["Prompt Compiler"])

    @router.post("/compile")
    def compile_prompt(payload: dict) -> dict:
        manifest = payload.get("executionManifest")
        manifest_id = str(payload.get("executionManifestId") or payload.get("manifestId") or "")
        if not isinstance(manifest, dict) and manifest_id and manifest_service:
            manifest = manifest_service.get(manifest_id)
            if not isinstance(manifest, dict):
                raise HTTPException(status_code=404, detail="Execution Manifest not found.")
        if not isinstance(manifest, dict):
            raise HTTPException(status_code=422, detail="executionManifest or executionManifestId is required.")
        try:
            return service.compile(manifest, str(payload.get("correlationId") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{compiled_prompt_id}")
    def get(compiled_prompt_id: str) -> dict:
        value = service.get(compiled_prompt_id)
        if not value:
            raise HTTPException(status_code=404, detail="Compiled Prompt not found.")
        return value

    return router
