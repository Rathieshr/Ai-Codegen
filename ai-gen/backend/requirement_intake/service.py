"""Deterministic requirement intake backed by the shared context pipeline."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from backend.context_orchestration.models import ContextRequest
from backend.platform.shared import JsonMapStore
from backend.requirement_analysis.summary import build_requirement_summary

from .ingestion import RequirementIngestionService


class RequirementIntakeService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        context_orchestrator: Any,
        artifact_writer: Callable[[dict[str, Any]], dict[str, Any]],
        ingestion_service: RequirementIngestionService | None = None,
        analysis_service: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.context_orchestrator = context_orchestrator
        self.artifact_writer = artifact_writer
        self.ingestion_service = ingestion_service or RequirementIngestionService(
            JsonMapStore(store.path.with_name("requirement_contexts.json")),
            platform=platform,
        )
        self.analysis_service = analysis_service
        self.platform = platform

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        requirement_context_id = str(request.get("requirementContextId") or "").strip()
        requirement = self.ingestion_service.get(requirement_context_id) if requirement_context_id else None
        if requirement_context_id and not requirement:
            raise ValueError("Requirement context was not found. Ingest the source before starting Planning.")
        if not requirement:
            # Compatibility path: legacy callers still pass through Requirement Intelligence first.
            ingestion_request = dict(request)
            ingestion_request["sourceType"] = ingestion_request.get("sourceType") or _legacy_source(request.get("inputType"))
            requirement = self.ingestion_service.ingest(ingestion_request)
        if not requirement.get("planningReady") or requirement.get("status") != "Ready":
            raise ValueError("Requirement context is not ready for Planning.")

        analysis = self.analysis_service.assert_approved(str(requirement.get("requirementId") or "")) if self.analysis_service else None
        readiness = analysis.get("planningReadiness", {}) if isinstance(analysis, dict) else {}
        if readiness.get("status") == "Blocked":
            reason = (readiness.get("blockers") or ["Requirement analysis blocked Planning."])[0]
            raise ValueError(str(reason))

        metadata = requirement.get("metadata") if isinstance(requirement.get("metadata"), dict) else {}
        input_type = str(requirement.get("sourceType") or "PasteRequirement")
        title = str(requirement.get("title") or "").strip()
        content = str((analysis or {}).get("planningRequirement") or requirement.get("normalizedRequirement") or "").strip()
        project_id = str(metadata.get("projectId") or "").strip()
        now = _now()
        requirement_id = str(requirement.get("requirementId") or "")
        correlation_id = str(requirement.get("correlationId") or request.get("correlationId") or "")
        requirement_summary = build_requirement_summary(requirement, analysis or {})
        context = self.context_orchestrator.orchestrate(ContextRequest(
            request_id=f"context_{requirement_id}",
            correlation_id=correlation_id,
            purpose="Planning",
            project_id=project_id,
            repository_id=str(metadata.get("repositoryId") or ""),
            branch=str(metadata.get("branch") or ""),
            artifact={
                "artifactId": requirement_id,
                "artifactType": "Requirement",
                "title": title,
                "description": content,
                "requirementSummary": requirement_summary,
                "planningSource": "RequirementSummary",
                "inputType": input_type,
                "requirementContextId": requirement_id,
                "requirementContextVersion": requirement.get("contextVersion"),
                "contentHash": requirement.get("contentHash"),
                "requirementAnalysisId": (analysis or {}).get("analysisId"),
                "requirementAnalysisStatus": readiness.get("status"),
            },
            options={
                "includePlanningLineage": True,
                "includeRepository": True,
                "includeKnowledge": True,
                "includeMemory": True,
                "includeStandards": True,
                "minimumConfidence": 0.5,
                "maxTokens": 4096,
            },
        ))
        source_summary = [
            {
                "source": item.get("sourceType"),
                "available": bool(item.get("available")),
                "selected": int(item.get("selectedCount") or 0),
                "freshness": item.get("freshness"),
                "version": item.get("version"),
            }
            for item in context.get("sourceSummary", [])
        ]
        pack_payload = {
            "planningSource": "RequirementSummary",
            "requirementSummary": requirement_summary,
            "requirement": {
                "requirementId": requirement_id,
                "inputType": input_type,
                "title": title,
                "content": content,
                "sourceWorkItemId": str(metadata.get("sourceReference") or ""),
                "requirementContextId": requirement_id,
                "requirementContextVersion": requirement.get("contextVersion"),
                "contentHash": requirement.get("contentHash"),
                "analysisId": (analysis or {}).get("analysisId"),
                "analysisStatus": readiness.get("status"),
            },
            "projectContext": {
                "organization": str(metadata.get("organization") or ""),
                "projectId": project_id,
                "projectName": str(metadata.get("projectName") or ""),
                "teamId": str(metadata.get("teamId") or ""),
                "repositoryId": str(metadata.get("repositoryId") or ""),
                "branch": str(metadata.get("branch") or ""),
            },
            "contextCapsule": {
                "capsuleId": context.get("capsuleId"),
                "status": context.get("status"),
                "confidence": context.get("confidence"),
                "freshnessStatus": context.get("freshnessStatus"),
                "sourceSummary": source_summary,
                "warnings": context.get("warnings", []),
                "blockers": context.get("blockers", []),
            },
            "recommendedHierarchy": {
                "epic": {"title": title, "status": "Proposed"},
                "features": [],
                "stories": [],
                "tasks": [],
            },
            "approval": {
                "required": True,
                "status": "Pending",
                "message": "Review and approve the Planning Pack before any Azure DevOps changes are prepared.",
            },
            "requirementAnalysis": {
                "analysisId": (analysis or {}).get("analysisId"),
                "summary": (analysis or {}).get("requirementSummary"),
                "planningReadiness": readiness,
                "qualityScore": (analysis or {}).get("requirementQualityScore"),
                "confidence": (analysis or {}).get("confidence"),
                "missingAcceptanceCriteria": (analysis or {}).get("missingAcceptanceCriteria", []),
                "ambiguousRequirements": (analysis or {}).get("ambiguousRequirements", []),
                "conflictingRequirements": (analysis or {}).get("conflictingRequirements", []),
                "duplicateRequirements": (analysis or {}).get("duplicateRequirements", []),
            },
        }
        artifact = self.artifact_writer({
            "artifact_type": "PlanningPack",
            "state": "draft",
            "title": title,
            "payload": pack_payload,
            "source_item": {"id": requirement_id, "type": "Requirement", "title": title},
            "created_by": str(request.get("actor") or metadata.get("createdBy") or "HEI User"),
        })
        result = {
            "requirementId": requirement_id,
            "planningPackId": artifact.get("artifact_id"),
            "title": title,
            "inputType": input_type,
            "sourceType": input_type,
            "requirementContextVersion": requirement.get("contextVersion"),
            "projectId": project_id,
            "status": "NeedsReview",
            "approvalRequired": True,
            "context": pack_payload["contextCapsule"],
            "requirementAnalysis": pack_payload["requirementAnalysis"],
            "createdAt": now,
            "correlationId": correlation_id,
            "durationMs": round((time.perf_counter() - started) * 1000, 2),
        }
        values = self.store.read(); values[requirement_id] = result; self.store.write(values)
        self._record(result, project_id)
        return result

    def list(self, project_id: str = "") -> dict[str, Any]:
        values = list(self.store.read().values())
        if project_id:
            values = [item for item in values if str(item.get("projectId") or project_id) == project_id]
        values.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
        return {"requirements": values, "count": len(values)}

    def get(self, requirement_id: str) -> dict[str, Any] | None:
        return self.store.read().get(requirement_id)

    def _record(self, result: dict[str, Any], project_id: str) -> None:
        if not self.platform:
            return
        payload = {
            "eventType": "PlanningPackCreated",
            "source": "CommandCenter",
            "projectId": project_id,
            "correlationId": result["correlationId"],
            "payload": {"requirementId": result["requirementId"], "planningPackId": result["planningPackId"]},
        }
        self.platform.events.publish(payload)
        self.platform.activity.add_activity({
            "activityType": "Planning",
            "title": "Planning Pack ready for review",
            "description": result["title"],
            "source": "CommandCenter",
            "projectId": project_id,
            "correlationId": result["correlationId"],
            "metadata": payload["payload"],
        })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _legacy_source(value: Any) -> str:
    normalized = str(value or "Business Requirement").strip()
    if normalized in {"PRD", "BRD"}:
        return "UploadDocument"
    if normalized == "Meeting Notes":
        return "MeetingTranscript"
    if normalized == "Azure DevOps Work Item":
        return "AzureDevOpsWorkItem"
    return "PasteRequirement"
