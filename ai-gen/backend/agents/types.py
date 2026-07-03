"""Shared models for the HEI Agent Orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


APPROVAL_CHECKPOINT = "Wait For Human Approval"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = clean(event.get("eventType") or event.get("type") or event.get("trigger")) or "Manual Trigger"
    return {
        "id": clean(event.get("id")) or f"event_{uuid4().hex[:12]}",
        "eventType": event_type,
        "source": clean(event.get("source")) or "Manual Trigger",
        "artifactType": clean(event.get("artifactType") or event.get("workItemType")),
        "artifactId": clean(event.get("artifactId") or event.get("workItemId")),
        "artifactTitle": clean(event.get("artifactTitle") or event.get("title")),
        "actor": clean(event.get("actor")) or "system",
        "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
        "createdAt": clean(event.get("createdAt")) or now_iso(),
    }


def normalize_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "projectId": clean(context.get("projectId") or context.get("project_id") or "default"),
        "repository": clean(context.get("repository")),
        "branch": clean(context.get("branch")),
        "workItem": context.get("workItem") if isinstance(context.get("workItem"), dict) else {},
        "parent": context.get("parent") if isinstance(context.get("parent"), dict) else {},
        "memoryContext": context.get("memoryContext") if isinstance(context.get("memoryContext"), dict) else {},
        "repositoryContext": context.get("repositoryContext") if isinstance(context.get("repositoryContext"), dict) else {},
        "approvalRequired": context.get("approvalRequired", True) is not False,
    }


def workflow_id() -> str:
    return f"workflow_{uuid4().hex[:12]}"


def workflow_event(message: str, status: str = "Completed", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"time": now_iso(), "message": message, "status": status, "metadata": metadata or {}}
