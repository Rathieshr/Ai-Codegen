"""Prompt Diagnostics REST API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


def build_prompt_diagnostics_router(service, manifest_service=None, package_service=None) -> APIRouter:
    router = APIRouter(prefix="/prompt-diagnostics", tags=["Prompt Diagnostics"])

    @router.post("/build")
    def build(payload: dict) -> dict:
        prompt = payload.get("optimizedPrompt")
        if not isinstance(prompt, dict):
            raise HTTPException(status_code=422, detail="optimizedPrompt is required.")

        manifest = payload.get("executionManifest")
        manifest_id = str(
            payload.get("executionManifestId")
            or prompt.get("sourceExecutionManifestId")
            or ""
        )
        if not isinstance(manifest, dict) and manifest_id and manifest_service:
            manifest = manifest_service.get(manifest_id)
        if not isinstance(manifest, dict):
            status = 404 if manifest_id else 422
            detail = "Execution Manifest not found." if manifest_id else "executionManifest or executionManifestId is required."
            raise HTTPException(status_code=status, detail=detail)

        package = payload.get("executionPackage")
        package_id = str(payload.get("executionPackageId") or manifest.get("sourcePackageId") or "")
        if not isinstance(package, dict) and package_id and package_service:
            package = package_service.get(package_id)
        try:
            return service.build(
                prompt,
                manifest,
                package if isinstance(package, dict) else None,
                payload.get("estimationProfile") if isinstance(payload.get("estimationProfile"), dict) else None,
                str(payload.get("correlationId") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/prompts/{optimized_prompt_id}")
    def get_by_prompt(optimized_prompt_id: str) -> dict:
        value = service.get_by_prompt(optimized_prompt_id)
        if not value:
            raise HTTPException(status_code=404, detail="Prompt Diagnostics not found.")
        return value

    @router.get("/{diagnostics_id}/summary")
    def summary(diagnostics_id: str) -> dict:
        value = service.summary(diagnostics_id)
        if not value:
            raise HTTPException(status_code=404, detail="Prompt Diagnostics not found.")
        return value

    @router.get("/{diagnostics_id}")
    def get(diagnostics_id: str) -> dict:
        value = service.get(diagnostics_id)
        if not value:
            raise HTTPException(status_code=404, detail="Prompt Diagnostics not found.")
        return value

    return router
