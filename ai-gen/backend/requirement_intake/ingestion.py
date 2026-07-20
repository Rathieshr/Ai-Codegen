"""Persisted, source-aware requirement ingestion."""

from __future__ import annotations

import base64
import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from backend.platform.shared import JsonMapStore

from .models import RequirementContext, RequirementDocument, RequirementMetadata, RequirementSourceType


FUTURE_SOURCE_MESSAGE = "This requirement source is reserved for a future connector and is not available in V1."
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


class RequirementIngestionService:
    """Converts every supported source into a stable RequirementContext."""

    def __init__(
        self,
        store: JsonMapStore,
        *,
        work_item_provider: Callable[[str, str], dict[str, Any] | None] | None = None,
        document_provider: Callable[[str], dict[str, Any] | None] | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.work_item_provider = work_item_provider
        self.document_provider = document_provider
        self.platform = platform

    def ingest(self, request: dict[str, Any]) -> dict[str, Any]:
        source_type = RequirementSourceType.parse(request.get("sourceType") or request.get("inputType"))
        if not source_type.available:
            raise ValueError(f"{source_type.value}: {FUTURE_SOURCE_MESSAGE}")

        project_id = _text(request.get("projectId"))
        if not project_id:
            raise ValueError("Azure DevOps project context is required.")

        title, content, documents, source_reference, source_revision = self._resolve(source_type, request, project_id)
        if not title:
            raise ValueError("Requirement title is required.")
        normalized = _normalize(content)
        if not normalized:
            raise ValueError("Requirement content is required.")

        now = _now()
        content_hash = _hash(f"{source_type.value}|{title}|{normalized}")
        requirement_id = _text(request.get("requirementId")) or f"requirement_{uuid4().hex}"
        correlation_id = _text(request.get("correlationId")) or f"corr_{uuid4().hex}"
        metadata = RequirementMetadata(
            project_id=project_id,
            project_name=_text(request.get("projectName")),
            organization=_text(request.get("organization")),
            team_id=_text(request.get("teamId")),
            repository_id=_text(request.get("repositoryId")),
            branch=_text(request.get("branch")),
            source_reference=source_reference,
            source_revision=source_revision,
            created_by=_text(request.get("actor")) or "HEI User",
            attributes={
                "iterationId": _text(request.get("iterationId")),
                "iterationPath": _text(request.get("iterationPath")),
                "repositoryName": _text(request.get("repositoryName")),
            },
        )
        context = RequirementContext(
            requirement_id=requirement_id,
            source_type=source_type,
            status="Ready",
            title=title,
            normalized_requirement=normalized,
            metadata=metadata,
            documents=documents,
            content_hash=content_hash,
            context_version="1.0",
            planning_ready=True,
            created_at=now,
            updated_at=now,
            correlation_id=correlation_id,
        )
        record = context.to_dict()
        values = self.store.read()
        values[requirement_id] = record
        self.store.write(values)
        self._publish("RequirementIngested", record)
        return record

    def get(self, requirement_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(requirement_id)
        return dict(value) if isinstance(value, dict) else None

    def status(self, requirement_id: str) -> dict[str, Any] | None:
        value = self.get(requirement_id)
        if not value:
            return None
        return {
            "requirementId": requirement_id,
            "sourceType": value.get("sourceType"),
            "status": value.get("status"),
            "planningReady": bool(value.get("planningReady")),
            "contextVersion": value.get("contextVersion"),
            "updatedAt": value.get("updatedAt"),
            "warnings": value.get("warnings", []),
        }

    def update(self, requirement_id: str, *, title: str, content: str, actor: str = "HEI User") -> dict[str, Any]:
        """Apply a human review edit while preserving source lineage."""
        current = self.get(requirement_id)
        if not current:
            raise ValueError("Requirement context was not found.")
        normalized = _normalize(content)
        if not title:
            raise ValueError("Requirement title is required.")
        if not normalized:
            raise ValueError("Requirement content is required.")
        source_type = str(current.get("sourceType") or RequirementSourceType.PASTE_REQUIREMENT.value)
        updated = dict(current)
        metadata = dict(updated.get("metadata") or {})
        metadata["lastEditedBy"] = actor or "HEI User"
        updated.update({
            "title": title,
            "normalizedRequirement": normalized,
            "contentHash": _hash(f"{source_type}|{title}|{normalized}"),
            "contextVersion": _next_version(str(current.get("contextVersion") or "1.0")),
            "status": "Ready",
            "planningReady": True,
            "updatedAt": _now(),
            "metadata": metadata,
        })
        values = self.store.read()
        values[requirement_id] = updated
        self.store.write(values)
        self._publish("RequirementContextUpdated", updated)
        return updated

    def update_repository(
        self, requirement_id: str, *, repository_id: str, repository_name: str, actor: str = "HEI User",
    ) -> dict[str, Any]:
        """Persist a reviewed repository selection without changing requirement text."""
        current = self.get(requirement_id)
        if not current:
            raise ValueError("Requirement context was not found.")
        metadata = dict(current.get("metadata") or {})
        attributes = dict(metadata.get("attributes") or {})
        if metadata.get("repositoryId") == repository_id and attributes.get("repositoryName") == repository_name:
            return current
        metadata["repositoryId"] = repository_id
        metadata["attributes"] = {
            **attributes,
            "repositoryName": repository_name,
            "repositorySelectedBy": actor or "HEI User",
            "repositorySelectedAt": _now(),
        }
        updated = {
            **current,
            "metadata": metadata,
            "contextVersion": _next_version(str(current.get("contextVersion") or "1.0")),
            "updatedAt": _now(),
        }
        values = self.store.read()
        values[requirement_id] = updated
        self.store.write(values)
        self._publish("RequirementRepositorySelected", updated)
        return updated

    def _resolve(
        self, source_type: RequirementSourceType, request: dict[str, Any], project_id: str,
    ) -> tuple[str, str, list[RequirementDocument], str, str]:
        if source_type == RequirementSourceType.AZURE_DEVOPS_WORK_ITEM:
            work_item_id = _text(request.get("workItemId") or request.get("sourceId"))
            if not work_item_id:
                raise ValueError("Azure DevOps work item ID is required.")
            item = self.work_item_provider(project_id, work_item_id) if self.work_item_provider else None
            if not item:
                raise ValueError("Azure DevOps work item is not available in the synchronized project cache.")
            title = _text(item.get("title") or item.get("System.Title"))
            description = _text(item.get("description") or item.get("System.Description"))
            criteria = item.get("acceptanceCriteria") or item.get("Microsoft.VSTS.Common.AcceptanceCriteria") or ""
            content = _text(request.get("requirementSummary")) or "\n\n".join(value for value in [description, _criteria_text(criteria)] if value)
            return title, content, [], work_item_id, _text(item.get("revision") or item.get("rev"))

        if source_type == RequirementSourceType.UPLOAD_DOCUMENT:
            document_id = _text(request.get("documentId"))
            if document_id:
                parsed_document = self.document_provider(document_id) if self.document_provider else None
                if not parsed_document:
                    raise ValueError("Requirement document is not parsed or ready for analysis.")
                content = _text(parsed_document.get("text"))
                document = RequirementDocument(
                    document_id=document_id,
                    name=_text(parsed_document.get("name")) or "requirement",
                    media_type=_text(parsed_document.get("mediaType")) or "application/octet-stream",
                    content_hash=_text(parsed_document.get("contentHash")) or _hash(content),
                    size_bytes=int(parsed_document.get("sizeBytes") or len(content.encode("utf-8"))),
                    text=content,
                    source="DocumentIngestion",
                    title=_text(parsed_document.get("title")),
                    document_type=_text(parsed_document.get("detectedType")) or "Unknown",
                    sections=[dict(item) for item in parsed_document.get("sections") or [] if isinstance(item, dict)],
                    metadata=dict(parsed_document.get("metadata") or {}),
                    pages=int(parsed_document.get("pages") or 0),
                    language=_text(parsed_document.get("language")) or "und",
                    extraction_log=[dict(item) for item in parsed_document.get("extractionLog") or [] if isinstance(item, dict)],
                )
                return _text(request.get("title")) or document.title or _title_from_name(document.name), content, [document], document_id, document.content_hash
            document_payload = request.get("document") if isinstance(request.get("document"), dict) else {}
            content = self._document_content(document_payload, request)
            name = _text(document_payload.get("name") or document_payload.get("fileName")) or "requirement.txt"
            media_type = _text(document_payload.get("mediaType") or document_payload.get("mimeType")) or "text/plain"
            encoded = content.encode("utf-8")
            if len(encoded) > MAX_DOCUMENT_BYTES:
                raise ValueError("Requirement document exceeds the 2 MB V1 ingestion limit.")
            document = RequirementDocument(
                document_id=f"document_{uuid4().hex}", name=name, media_type=media_type,
                content_hash=_hash(content), size_bytes=len(encoded), text=_normalize(content), source="Upload",
            )
            return _text(request.get("title")) or _title_from_name(name), content, [document], name, ""

        content = _text(request.get("content") or request.get("transcript"))
        title = _text(request.get("title"))
        if source_type == RequirementSourceType.MEETING_TRANSCRIPT:
            document = RequirementDocument(
                document_id=f"document_{uuid4().hex}", name=_text(request.get("meetingTitle")) or f"{title or 'Meeting'} transcript",
                media_type="text/plain", content_hash=_hash(content), size_bytes=len(content.encode("utf-8")),
                text=_normalize(content), source="MeetingTranscript",
            )
            return title or document.name, content, [document], _text(request.get("meetingId")), ""
        return title, content, [], "", ""

    @staticmethod
    def _document_content(document: dict[str, Any], request: dict[str, Any]) -> str:
        value = document.get("content") if document else request.get("content")
        if _text(document.get("encoding")).lower() == "base64":
            try:
                return base64.b64decode(_text(value), validate=True).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as error:
                raise ValueError("Uploaded document is not valid UTF-8 base64 content.") from error
        return _text(value)

    def _publish(self, event_type: str, context: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "RequirementIntelligence",
            "projectId": context.get("metadata", {}).get("projectId", ""),
            "correlationId": context.get("correlationId", ""),
            "payload": {
                "requirementId": context.get("requirementId"),
                "sourceType": context.get("sourceType"),
                "contextVersion": context.get("contextVersion"),
            },
        })


def _normalize(value: Any) -> str:
    text = html.unescape(_text(value))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = [re.sub(r"\s+", " ", line).strip(" -\t") for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _criteria_text(value: Any) -> str:
    if isinstance(value, list):
        return "Acceptance Criteria:\n" + "\n".join(f"- {_text(item)}" for item in value if _text(item))
    text = _text(value)
    return f"Acceptance Criteria:\n{text}" if text else ""


def _title_from_name(name: str) -> str:
    stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"[_-]+", " ", stem).strip().title()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_version(value: str) -> str:
    try:
        major = int(value.split(".", 1)[0])
    except (TypeError, ValueError):
        major = 1
    return f"{major + 1}.0"
