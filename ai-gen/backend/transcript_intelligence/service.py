"""Persistent transcript upload, analysis, and requirement-context creation."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.document_ingestion import DocumentIngestionService
from backend.platform.shared import JsonMapStore
from backend.requirement_intake import RequirementIngestionService

from .analyzer import TranscriptAnalyzer
from .models import TranscriptAnalysis, TranscriptSourceType


class TranscriptNotFoundError(LookupError):
    pass


class TranscriptValidationError(ValueError):
    pass


class TranscriptIntelligenceService:
    def __init__(
        self,
        storage_root: Path,
        *,
        document_service: DocumentIngestionService,
        requirement_ingestion: RequirementIngestionService,
        analyzer: TranscriptAnalyzer | None = None,
        platform: Any | None = None,
    ) -> None:
        storage_root.mkdir(parents=True, exist_ok=True)
        self.store = JsonMapStore(storage_root / "transcripts.json")
        self.document_service = document_service
        self.requirement_ingestion = requirement_ingestion
        self.analyzer = analyzer or TranscriptAnalyzer()
        self.platform = platform

    def upload(self, request: dict[str, Any]) -> dict[str, Any]:
        file_name = str(request.get("fileName") or "").strip()
        try:
            source_type = TranscriptSourceType.parse(request.get("sourceType"), file_name=file_name)
        except ValueError as error:
            raise TranscriptValidationError(str(error)) from error
        document_id = ""
        if source_type in {TranscriptSourceType.DOCX, TranscriptSourceType.TXT}:
            if not file_name:
                raise TranscriptValidationError("Transcript file name is required.")
            uploaded = self.document_service.upload(request)
            parsed = self.document_service.parse(str(uploaded["documentId"]))
            document_id = str(parsed["documentId"])
            requirement_document = self.document_service.requirement_document(document_id) or {}
            text = str(requirement_document.get("text") or "")
            if not text.strip():
                raise TranscriptValidationError("Transcript document did not contain readable text.")
        else:
            text = str(request.get("transcript") or request.get("content") or "")
            if not text.strip():
                raise TranscriptValidationError("Transcript content is required.")

        transcript_id = f"transcript_{uuid4().hex}"
        now = _now()
        record = {
            "transcriptId": transcript_id,
            "sourceType": source_type.value,
            "status": "Uploaded",
            "title": str(request.get("title") or request.get("meetingTitle") or "").strip(),
            "date": str(request.get("date") or request.get("meetingDate") or "").strip(),
            "transcript": text,
            "documentId": document_id,
            "projectId": str(request.get("projectId") or "").strip(),
            "projectName": str(request.get("projectName") or "").strip(),
            "organization": str(request.get("organization") or "").strip(),
            "teamId": str(request.get("teamId") or "").strip(),
            "repositoryId": str(request.get("repositoryId") or "").strip(),
            "repositoryName": str(request.get("repositoryName") or "").strip(),
            "branch": str(request.get("branch") or "").strip(),
            "actor": str(request.get("actor") or "HEI User").strip(),
            "correlationId": str(request.get("correlationId") or f"corr_{uuid4().hex}"),
            "contentHash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "analysis": {},
            "requirementContextId": "",
            "createdAt": now,
            "updatedAt": now,
            "extractionLog": [{"stage": "Upload", "status": "Completed", "message": f"Normalized {source_type.value} transcript.", "timestamp": now}],
            "error": "",
        }
        self._save(record)
        self._publish("MeetingTranscriptUploaded", record)
        return _public(record)

    def analyze(self, transcript_id: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self._get(transcript_id)
        options = request or {}
        record["status"] = "Analyzing"
        record["updatedAt"] = _now()
        self._save(record)
        try:
            analysis = self.analyzer.analyze(
                str(record.get("transcript") or ""),
                title=str(options.get("title") or record.get("title") or ""),
                meeting_date=str(options.get("date") or record.get("date") or ""),
            )
            record["analysis"] = analysis.to_dict()
            record["title"] = analysis.meeting_title
            record["date"] = analysis.meeting_date
            record["status"] = "Ready" if analysis.ready_for_planning else "NeedsReview"
            record["updatedAt"] = _now()
            record["extractionLog"].append({
                "stage": "Analysis",
                "status": "Completed",
                "message": f"Found {len(analysis.requirements)} requirements and {len(analysis.decisions)} decisions.",
                "timestamp": record["updatedAt"],
            })
            if analysis.ready_for_planning and record.get("projectId"):
                context = self.requirement_ingestion.ingest(self._requirement_request(record, analysis))
                record["requirementContextId"] = context["requirementId"]
            self._save(record)
            self._publish("MeetingTranscriptAnalyzed", record)
            return _public(record)
        except Exception as error:
            record["status"] = "Failed"
            record["error"] = str(error)
            record["updatedAt"] = _now()
            record["extractionLog"].append({"stage": "Analysis", "status": "Failed", "message": str(error), "timestamp": record["updatedAt"]})
            self._save(record)
            self._publish("MeetingTranscriptAnalysisFailed", record)
            raise

    def get(self, transcript_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(transcript_id)
        return _public(value) if isinstance(value, dict) else None

    def _get(self, transcript_id: str) -> dict[str, Any]:
        value = self.store.read().get(transcript_id)
        if not isinstance(value, dict):
            raise TranscriptNotFoundError(transcript_id)
        return dict(value)

    def _save(self, record: dict[str, Any]) -> None:
        values = self.store.read()
        values[str(record["transcriptId"])] = record
        self.store.write(values)

    @staticmethod
    def _requirement_request(record: dict[str, Any], analysis: TranscriptAnalysis) -> dict[str, Any]:
        sections = [
            ("Meeting Summary", [analysis.meeting_summary]),
            ("Business Decisions", [item.text for item in analysis.decisions]),
            ("Engineering Requirements", [item.text for item in analysis.requirements]),
            ("Action Items", [item.text for item in analysis.action_items]),
            ("Risks", [item.text for item in analysis.risks]),
            ("Open Questions", [item.text for item in analysis.open_questions]),
            ("Dependencies", [item.text for item in analysis.dependencies]),
        ]
        curated = "\n\n".join(
            f"{heading}:\n" + "\n".join(f"- {item}" for item in items)
            for heading, items in sections if any(item.strip() for item in items)
        )
        return {
            "sourceType": "MeetingTranscript",
            "title": analysis.meeting_title,
            "meetingTitle": analysis.meeting_title,
            "meetingId": record["transcriptId"],
            "content": curated,
            "projectId": record.get("projectId"),
            "projectName": record.get("projectName"),
            "organization": record.get("organization"),
            "teamId": record.get("teamId"),
            "repositoryId": record.get("repositoryId"),
            "repositoryName": record.get("repositoryName"),
            "branch": record.get("branch"),
            "actor": record.get("actor"),
            "correlationId": record.get("correlationId"),
        }

    def _publish(self, event_type: str, record: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "RequirementIntelligence",
            "projectId": record.get("projectId", ""),
            "correlationId": record.get("correlationId", ""),
            "payload": {"transcriptId": record.get("transcriptId"), "status": record.get("status")},
        })


def _public(record: dict[str, Any]) -> dict[str, Any]:
    value = dict(record)
    value.pop("transcript", None)
    value["readyForPlanning"] = bool((value.get("analysis") or {}).get("readyForPlanning"))
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
