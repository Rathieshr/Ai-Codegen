"""Meeting transcript upload and intelligence APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from .service import TranscriptIntelligenceService, TranscriptNotFoundError, TranscriptValidationError


def build_transcript_intelligence_router(service: TranscriptIntelligenceService) -> APIRouter:
    router = APIRouter(tags=["HEI Meeting Transcript Intelligence"])

    @router.post("/transcripts/upload")
    def upload_transcript(request: dict[str, Any] = Body(...)):
        try:
            return service.upload(request)
        except TranscriptValidationError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_transcript", "message": str(error)}})
        except ValueError as error:
            return JSONResponse(status_code=422, content={"error": {"code": "transcript_parse_failed", "message": str(error)}})

    @router.post("/transcripts/analyze")
    def analyze_transcript(request: dict[str, Any] = Body(...)):
        transcript_id = str(request.get("transcriptId") or "").strip()
        if not transcript_id:
            return JSONResponse(status_code=400, content={"error": {"code": "transcript_id_required", "message": "Transcript ID is required."}})
        try:
            return service.analyze(transcript_id, request)
        except TranscriptNotFoundError:
            return JSONResponse(status_code=404, content={"error": {"code": "transcript_not_found", "message": "Transcript was not found."}})
        except Exception as error:
            return JSONResponse(status_code=422, content={"error": {"code": "transcript_analysis_failed", "message": str(error), "transcriptId": transcript_id}})

    @router.get("/transcripts/{transcript_id}")
    def get_transcript(transcript_id: str):
        value = service.get(transcript_id)
        if value is None:
            return JSONResponse(status_code=404, content={"error": {"code": "transcript_not_found", "message": "Transcript was not found."}})
        return value

    return router
