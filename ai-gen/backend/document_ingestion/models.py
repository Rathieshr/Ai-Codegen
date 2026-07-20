"""Canonical document-ingestion models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class DocumentFormat(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"
    TXT = "TXT"
    MARKDOWN = "Markdown"


class DetectedDocumentType(str, Enum):
    PRD = "PRD"
    BRD = "BRD"
    SRS = "SRS"
    FUNCTIONAL_SPECIFICATION = "Functional Specification"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class DocumentSection:
    title: str
    level: int
    text: str
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    detected_type: DetectedDocumentType
    sections: list[DocumentSection]
    text: str
    metadata: dict[str, Any]
    pages: int
    language: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "detectedType": self.detected_type.value,
            "sections": [section.to_dict() for section in self.sections],
            "text": self.text,
            "metadata": dict(self.metadata),
            "pages": self.pages,
            "language": self.language,
        }


@dataclass
class DocumentRecord:
    document_id: str
    file_name: str
    media_type: str
    document_format: DocumentFormat
    status: str
    size_bytes: int
    content_hash: str
    original_storage_key: str
    created_at: str
    updated_at: str
    created_by: str = "HEI User"
    project_id: str = ""
    parsed_storage_key: str = ""
    parsed: dict[str, Any] = field(default_factory=dict)
    extraction_log: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        parsed = dict(self.parsed)
        if not include_text:
            parsed.pop("text", None)
        return {
            "documentId": self.document_id,
            "fileName": self.file_name,
            "mediaType": self.media_type,
            "format": self.document_format.value,
            "status": self.status,
            "sizeBytes": self.size_bytes,
            "contentHash": self.content_hash,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "createdBy": self.created_by,
            "projectId": self.project_id,
            "parsed": parsed,
            "extractionLog": list(self.extraction_log),
            "error": self.error,
            "readyForAnalysis": self.status == "Ready",
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentRecord":
        return cls(
            document_id=str(value.get("documentId") or ""),
            file_name=str(value.get("fileName") or ""),
            media_type=str(value.get("mediaType") or ""),
            document_format=DocumentFormat(str(value.get("format") or "TXT")),
            status=str(value.get("status") or "Uploaded"),
            size_bytes=int(value.get("sizeBytes") or 0),
            content_hash=str(value.get("contentHash") or ""),
            original_storage_key=str(value.get("originalStorageKey") or ""),
            created_at=str(value.get("createdAt") or ""),
            updated_at=str(value.get("updatedAt") or ""),
            created_by=str(value.get("createdBy") or "HEI User"),
            project_id=str(value.get("projectId") or ""),
            parsed_storage_key=str(value.get("parsedStorageKey") or ""),
            parsed=dict(value.get("parsed") or {}),
            extraction_log=[dict(item) for item in value.get("extractionLog") or [] if isinstance(item, dict)],
            error=str(value.get("error") or ""),
        )

    def to_storage_dict(self) -> dict[str, Any]:
        value = self.to_dict(include_text=True)
        value["originalStorageKey"] = self.original_storage_key
        value["parsedStorageKey"] = self.parsed_storage_key
        return value


def _camel(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key.split("_")[0] + "".join(part.capitalize() for part in key.split("_")[1:]): item
        for key, item in value.items()
    }
