"""Document upload and parsing APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from .service import DocumentIngestionService, DocumentNotFoundError, DocumentParsingFailed, DocumentValidationError


def build_document_ingestion_router(service: DocumentIngestionService) -> APIRouter:
    router = APIRouter(tags=["HEI Requirement Documents"])

    @router.post("/documents/upload")
    def upload(request: dict[str, Any] = Body(...)):
        try:
            return service.upload(request)
        except DocumentValidationError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_document", "message": str(error)}})

    @router.get("/documents/{document_id}")
    def get_document(document_id: str):
        value = service.get(document_id)
        if value is None:
            return JSONResponse(status_code=404, content={"error": {"code": "document_not_found", "message": "Document was not found."}})
        return value

    @router.post("/documents/{document_id}/parse")
    def parse_document(document_id: str, request: dict[str, Any] | None = Body(default=None)):
        try:
            return service.parse(document_id, force=bool((request or {}).get("force")))
        except DocumentNotFoundError:
            return JSONResponse(status_code=404, content={"error": {"code": "document_not_found", "message": "Document was not found."}})
        except DocumentParsingFailed as error:
            return JSONResponse(status_code=422, content={"error": {"code": "document_parse_failed", "message": str(error), "documentId": error.document_id}})

    return router
