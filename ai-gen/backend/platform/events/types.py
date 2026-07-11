"""Platform event types and normalization helpers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..shared import OperationSource, as_dict, clean, enum_value, generated_id, now_iso


class PlatformEventType(str, Enum):
    EXECUTION_PACKAGE_REQUESTED = "ExecutionPackageRequested"
    EXECUTION_PACKAGE_BUILT = "ExecutionPackageBuilt"
    EXECUTION_PACKAGE_READY = "ExecutionPackageReady"
    EXECUTION_PACKAGE_FAILED = "ExecutionPackageFailed"
    CONTEXT_ORCHESTRATION_REQUESTED = "ContextOrchestrationRequested"
    CONTEXT_ORCHESTRATION_COMPLETED = "ContextOrchestrationCompleted"
    CONTEXT_ORCHESTRATION_NEEDS_REVIEW = "ContextOrchestrationNeedsReview"
    CONTEXT_ORCHESTRATION_FAILED = "ContextOrchestrationFailed"
    REPOSITORY_REGISTERED = "RepositoryRegistered"
    REPOSITORY_SCAN_REQUESTED = "RepositoryScanRequested"
    REPOSITORY_SCAN_COMPLETED = "RepositoryScanCompleted"
    REPOSITORY_SCAN_FAILED = "RepositoryScanFailed"
    WORK_ITEM_CREATED = "WorkItemCreated"
    WORK_ITEM_UPDATED = "WorkItemUpdated"
    PLANNING_PACK_CREATED = "PlanningPackCreated"
    PLANNING_PACK_APPROVED = "PlanningPackApproved"
    EXECUTION_PACK_CREATED = "ExecutionPackCreated"
    EXECUTION_PACK_APPROVED = "ExecutionPackApproved"
    PULL_REQUEST_CREATED = "PullRequestCreated"
    PULL_REQUEST_UPDATED = "PullRequestUpdated"
    PULL_REQUEST_MERGED = "PullRequestMerged"
    VALIDATION_REQUESTED = "ValidationRequested"
    VALIDATION_COMPLETED = "ValidationCompleted"
    QA_PACK_CREATED = "QAPackCreated"
    MEMORY_CAPTURE_REQUESTED = "MemoryCaptureRequested"
    MEMORY_CAPTURE_APPROVED = "MemoryCaptureApproved"
    AGENT_RUN_REQUESTED = "AgentRunRequested"
    AGENT_RUN_COMPLETED = "AgentRunCompleted"
    AGENT_RUN_FAILED = "AgentRunFailed"


def normalize_platform_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = clean(event.get("eventType") or event.get("type")) or PlatformEventType.WORK_ITEM_UPDATED.value
    return {
        "eventId": clean(event.get("eventId") or event.get("id")) or generated_id("platform_event"),
        "eventType": event_type,
        "source": enum_value(event.get("source"), OperationSource, OperationSource.MANUAL),
        "projectId": clean(event.get("projectId") or event.get("project_id")),
        "repositoryId": clean(event.get("repositoryId") or event.get("repository_id")),
        "workItemId": clean(event.get("workItemId") or event.get("work_item_id")),
        "correlationId": clean(event.get("correlationId") or event.get("correlation_id")) or generated_id("corr"),
        "payload": as_dict(event.get("payload")),
        "createdAt": clean(event.get("createdAt")) or now_iso(),
    }
