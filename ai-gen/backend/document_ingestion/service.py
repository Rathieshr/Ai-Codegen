"""Persistent upload and parsing lifecycle for requirement documents."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.platform.shared import JsonMapStore

from .models import DocumentFormat, DocumentRecord
from .parser import DocumentParseError, DocumentParser


MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
FORMAT_BY_SUFFIX = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".txt": DocumentFormat.TXT,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
}
MEDIA_TYPES = {
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentFormat.TXT: "text/plain",
    DocumentFormat.MARKDOWN: "text/markdown",
}


class DocumentNotFoundError(LookupError):
    pass


class DocumentValidationError(ValueError):
    pass


class DocumentParsingFailed(ValueError):
    def __init__(self, document_id: str, message: str) -> None:
        super().__init__(message)
        self.document_id = document_id


class DocumentIngestionService:
    def __init__(self, storage_root: Path, *, parser: DocumentParser | None = None, platform: Any | None = None) -> None:
        self.storage_root = storage_root
        self.original_root = storage_root / "originals"
        self.parsed_root = storage_root / "parsed"
        self.original_root.mkdir(parents=True, exist_ok=True)
        self.parsed_root.mkdir(parents=True, exist_ok=True)
        self.store = JsonMapStore(storage_root / "documents.json")
        self.parser = parser or DocumentParser()
        self.platform = platform

    def upload(self, request: dict[str, Any]) -> dict[str, Any]:
        file_name = _safe_file_name(request.get("fileName") or request.get("name"))
        document_format = _format(file_name, request.get("mediaType"))
        content = _decode_content(request)
        if not content:
            raise DocumentValidationError("Uploaded document is empty.")
        if len(content) > MAX_DOCUMENT_BYTES:
            raise DocumentValidationError("Document exceeds the 25 MB upload limit.")
        _validate_signature(document_format, content)

        document_id = f"document_{uuid4().hex}"
        suffix = Path(file_name).suffix.lower()
        storage_key = f"originals/{document_id}{suffix}"
        (self.storage_root / storage_key).write_bytes(content)
        now = _now()
        record = DocumentRecord(
            document_id=document_id,
            file_name=file_name,
            media_type=str(request.get("mediaType") or MEDIA_TYPES[document_format]),
            document_format=document_format,
            status="Uploaded",
            size_bytes=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
            original_storage_key=storage_key,
            created_at=now,
            updated_at=now,
            created_by=str(request.get("actor") or "HEI User"),
            project_id=str(request.get("projectId") or ""),
            extraction_log=[{"stage": "Uploaded", "status": "Completed", "message": f"Stored original {document_format.value} document.", "timestamp": now}],
        )
        self._save(record)
        self._publish("RequirementDocumentUploaded", record)
        return record.to_dict(include_text=False)

    def parse(self, document_id: str, *, force: bool = False) -> dict[str, Any]:
        record = self._record(document_id)
        if record.status == "Ready" and not force:
            return record.to_dict()
        record.status = "Parsing"
        record.error = ""
        record.updated_at = _now()
        record.extraction_log.append({"stage": "Parsing", "status": "Started", "message": "Document extraction started.", "timestamp": record.updated_at})
        self._save(record)
        try:
            content = (self.storage_root / record.original_storage_key).read_bytes()
            parsed, log = self.parser.parse(content, record.document_format, record.file_name)
            parsed_key = f"parsed/{record.document_id}.txt"
            (self.storage_root / parsed_key).write_text(parsed.text, encoding="utf-8")
            record.parsed_storage_key = parsed_key
            record.parsed = parsed.to_dict()
            record.status = "Ready"
            record.updated_at = _now()
            record.extraction_log.extend({**item, "timestamp": record.updated_at} for item in log)
            self._save(record)
            self._publish("RequirementDocumentParsed", record)
            return record.to_dict()
        except (DocumentParseError, OSError) as error:
            record.status = "Failed"
            record.error = str(error)
            record.updated_at = _now()
            record.extraction_log.append({"stage": "ParseFailed", "status": "Failed", "message": str(error), "timestamp": record.updated_at})
            self._save(record)
            self._publish("RequirementDocumentParseFailed", record)
            raise DocumentParsingFailed(document_id, str(error)) from error

    def get(self, document_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(document_id)
        if not isinstance(value, dict):
            return None
        return DocumentRecord.from_dict(value).to_dict()

    def requirement_document(self, document_id: str) -> dict[str, Any] | None:
        value = self.get(document_id)
        if not value or value.get("status") != "Ready":
            return None
        parsed = value.get("parsed") if isinstance(value.get("parsed"), dict) else {}
        return {
            "documentId": value.get("documentId"),
            "name": value.get("fileName"),
            "mediaType": value.get("mediaType"),
            "contentHash": value.get("contentHash"),
            "sizeBytes": value.get("sizeBytes"),
            "text": parsed.get("text", ""),
            "title": parsed.get("title", ""),
            "detectedType": parsed.get("detectedType", "Unknown"),
            "metadata": parsed.get("metadata", {}),
            "pages": parsed.get("pages", 0),
            "language": parsed.get("language", "und"),
            "sections": parsed.get("sections", []),
            "extractionLog": value.get("extractionLog", []),
        }

    def _record(self, document_id: str) -> DocumentRecord:
        value = self.store.read().get(document_id)
        if not isinstance(value, dict):
            raise DocumentNotFoundError(document_id)
        return DocumentRecord.from_dict(value)

    def _save(self, record: DocumentRecord) -> None:
        values = self.store.read()
        values[record.document_id] = record.to_storage_dict()
        self.store.write(values)

    def _publish(self, event_type: str, record: DocumentRecord) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "RequirementIntelligence",
            "projectId": record.project_id,
            "payload": {"documentId": record.document_id, "status": record.status, "format": record.document_format.value},
        })


def _decode_content(request: dict[str, Any]) -> bytes:
    encoded = request.get("contentBase64")
    if encoded not in (None, ""):
        try:
            return base64.b64decode(str(encoded), validate=True)
        except (binascii.Error, ValueError) as error:
            raise DocumentValidationError("Document content is not valid base64.") from error
    content = request.get("content")
    return str(content or "").encode("utf-8")


def _safe_file_name(value: Any) -> str:
    name = Path(str(value or "").replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise DocumentValidationError("Document file name is required.")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:220]


def _format(file_name: str, media_type: Any) -> DocumentFormat:
    suffix = Path(file_name).suffix.lower()
    document_format = FORMAT_BY_SUFFIX.get(suffix)
    if not document_format:
        raise DocumentValidationError("Unsupported document format. Upload PDF, DOCX, TXT, or Markdown.")
    supplied = str(media_type or "").lower()
    allowed = {MEDIA_TYPES[document_format], "application/octet-stream", ""}
    if supplied not in allowed and not (document_format == DocumentFormat.MARKDOWN and supplied == "text/plain"):
        raise DocumentValidationError("Document media type does not match the file extension.")
    return document_format


def _validate_signature(document_format: DocumentFormat, content: bytes) -> None:
    if document_format == DocumentFormat.PDF and not content.startswith(b"%PDF-"):
        raise DocumentValidationError("The uploaded file is not a valid PDF.")
    if document_format == DocumentFormat.DOCX and not content.startswith(b"PK"):
        raise DocumentValidationError("The uploaded file is not a valid DOCX container.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
