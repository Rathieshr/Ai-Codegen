"""Canonical models for requirement-source ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RequirementSourceType(str, Enum):
    PASTE_REQUIREMENT = "PasteRequirement"
    UPLOAD_DOCUMENT = "UploadDocument"
    AZURE_DEVOPS_WORK_ITEM = "AzureDevOpsWorkItem"
    MEETING_TRANSCRIPT = "MeetingTranscript"
    CONFLUENCE = "Confluence"
    SHAREPOINT = "SharePoint"
    NOTION = "Notion"
    EMAIL = "Email"
    REST_API = "RestApi"

    @classmethod
    def parse(cls, value: Any) -> "RequirementSourceType":
        normalized = "".join(character for character in str(value or "") if character.isalnum()).lower()
        aliases = {
            "": cls.PASTE_REQUIREMENT,
            "pasterequirement": cls.PASTE_REQUIREMENT,
            "businessrequirement": cls.PASTE_REQUIREMENT,
            "bugreport": cls.PASTE_REQUIREMENT,
            "customerrequest": cls.PASTE_REQUIREMENT,
            "prd": cls.UPLOAD_DOCUMENT,
            "brd": cls.UPLOAD_DOCUMENT,
            "uploaddocument": cls.UPLOAD_DOCUMENT,
            "azuredevopsworkitem": cls.AZURE_DEVOPS_WORK_ITEM,
            "meetingnotes": cls.MEETING_TRANSCRIPT,
            "meetingtranscript": cls.MEETING_TRANSCRIPT,
            "confluence": cls.CONFLUENCE,
            "sharepoint": cls.SHAREPOINT,
            "notion": cls.NOTION,
            "email": cls.EMAIL,
            "restapi": cls.REST_API,
        }
        if normalized not in aliases:
            raise ValueError(f"Unsupported requirement source type '{value}'.")
        return aliases[normalized]

    @property
    def available(self) -> bool:
        return self in {
            self.PASTE_REQUIREMENT,
            self.UPLOAD_DOCUMENT,
            self.AZURE_DEVOPS_WORK_ITEM,
            self.MEETING_TRANSCRIPT,
        }


@dataclass(frozen=True)
class RequirementMetadata:
    project_id: str
    project_name: str = ""
    organization: str = ""
    team_id: str = ""
    repository_id: str = ""
    branch: str = ""
    source_reference: str = ""
    source_revision: str = ""
    created_by: str = "HEI User"
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class RequirementDocument:
    document_id: str
    name: str
    media_type: str
    content_hash: str
    size_bytes: int
    text: str
    source: str
    title: str = ""
    document_type: str = "Unknown"
    sections: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: int = 0
    language: str = "und"
    extraction_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        value = _camel(asdict(self))
        if not include_text:
            value.pop("text", None)
        return value


@dataclass(frozen=True)
class RequirementContext:
    requirement_id: str
    source_type: RequirementSourceType
    status: str
    title: str
    normalized_requirement: str
    metadata: RequirementMetadata
    documents: list[RequirementDocument]
    content_hash: str
    context_version: str
    planning_ready: bool
    created_at: str
    updated_at: str
    correlation_id: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self, *, include_document_text: bool = True) -> dict[str, Any]:
        return {
            "requirementId": self.requirement_id,
            "sourceType": self.source_type.value,
            "status": self.status,
            "title": self.title,
            "normalizedRequirement": self.normalized_requirement,
            "metadata": self.metadata.to_dict(),
            "documents": [item.to_dict(include_text=include_document_text) for item in self.documents],
            "contentHash": self.content_hash,
            "contextVersion": self.context_version,
            "planningReady": self.planning_ready,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "correlationId": self.correlation_id,
            "warnings": list(self.warnings),
        }


def _camel(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key.split("_")[0] + "".join(part.capitalize() for part in key.split("_")[1:]): item
        for key, item in value.items()
    }
