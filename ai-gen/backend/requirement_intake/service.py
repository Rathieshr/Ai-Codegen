"""Deterministic requirement intake backed by the shared context pipeline."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Callable

from backend.context_orchestration.models import ContextRequest
from backend.platform.shared import JsonMapStore


SUPPORTED_INPUT_TYPES = {
    "Business Requirement",
    "PRD",
    "BRD",
    "Meeting Notes",
    "Bug Report",
    "Azure DevOps Work Item",
    "Customer Request",
}


class RequirementIntakeService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        context_orchestrator: Any,
        artifact_writer: Callable[[dict[str, Any]], dict[str, Any]],
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.context_orchestrator = context_orchestrator
        self.artifact_writer = artifact_writer
        self.platform = platform

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        input_type = str(request.get("inputType") or "Business Requirement").strip()
        title = str(request.get("title") or "").strip()
        content = str(request.get("content") or "").strip()
        project_id = str(request.get("projectId") or "").strip()
        if input_type not in SUPPORTED_INPUT_TYPES:
            raise ValueError(f"Unsupported requirement input type '{input_type}'.")
        if not title:
            raise ValueError("Requirement title is required.")
        if not content:
            raise ValueError("Requirement content is required.")
        if not project_id:
            raise ValueError("Azure DevOps project context is required.")

        now = _now()
        digest = hashlib.sha256(f"{project_id}|{input_type}|{title}|{content}|{now}".encode()).hexdigest()[:14]
        requirement_id = f"requirement_{digest}"
        correlation_id = str(request.get("correlationId") or f"corr_{digest}")
        context = self.context_orchestrator.orchestrate(ContextRequest(
            request_id=f"context_{digest}",
            correlation_id=correlation_id,
            purpose="Planning",
            project_id=project_id,
            repository_id=str(request.get("repositoryId") or ""),
            branch=str(request.get("branch") or ""),
            artifact={
                "artifactId": requirement_id,
                "artifactType": "Requirement",
                "title": title,
                "description": content,
                "inputType": input_type,
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
            "requirement": {
                "requirementId": requirement_id,
                "inputType": input_type,
                "title": title,
                "content": content,
                "sourceWorkItemId": str(request.get("workItemId") or ""),
            },
            "projectContext": {
                "organization": str(request.get("organization") or ""),
                "projectId": project_id,
                "projectName": str(request.get("projectName") or ""),
                "teamId": str(request.get("teamId") or ""),
                "repositoryId": str(request.get("repositoryId") or ""),
                "branch": str(request.get("branch") or ""),
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
        }
        artifact = self.artifact_writer({
            "artifact_type": "PlanningPack",
            "state": "draft",
            "title": title,
            "payload": pack_payload,
            "source_item": {"id": requirement_id, "type": "Requirement", "title": title},
            "created_by": str(request.get("actor") or "HEI User"),
        })
        result = {
            "requirementId": requirement_id,
            "planningPackId": artifact.get("artifact_id"),
            "title": title,
            "inputType": input_type,
            "projectId": project_id,
            "status": "NeedsReview",
            "approvalRequired": True,
            "context": pack_payload["contextCapsule"],
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
