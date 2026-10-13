"""Persistent Azure DevOps agent run and approval-pack models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentTrigger(str, Enum):
    REQUIREMENT_RECEIVED = "RequirementReceived"
    PLANNING_PACK_APPROVED = "PlanningPackApproved"
    WORK_ITEM_CHANGED = "WorkItemChanged"
    SPRINT_STARTED = "SprintStarted"
    SPRINT_NEARING_END = "SprintNearingEnd"
    PULL_REQUEST_CREATED = "PullRequestCreated"
    PULL_REQUEST_UPDATED = "PullRequestUpdated"
    PULL_REQUEST_MERGED = "PullRequestMerged"
    BUILD_FAILED = "BuildFailed"
    SCHEDULED_RECONCILIATION = "ScheduledReconciliation"
    MANUAL_REQUEST = "ManualRequest"


class ActionPackStatus(str, Enum):
    PREPARED = "Prepared"
    PENDING_APPROVAL = "PendingApproval"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    STALE = "Stale"
    APPLYING = "Applying"
    APPLIED = "Applied"
    PARTIAL = "Partial"
    FAILED = "Failed"
    POLICY_DENIED = "PolicyDenied"


@dataclass
class AzureDevOpsActionPack:
    pack_id: str
    trigger: str
    source_entities: list[dict[str, Any]]
    proposed_actions: list[dict[str, Any]]
    dry_run: dict[str, Any]
    risks: list[str]
    warnings: list[str]
    required_permissions: list[str]
    approval_status: str
    expires_at: str
    source_revisions: dict[str, str]
    correlation_id: str
    run_id: str = ""
    project_id: str = ""
    connection_id: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    approved_by: str = ""
    approved_at: str = ""
    rejected_by: str = ""
    rejected_at: str = ""
    applied_by: str = ""
    applied_at: str = ""
    application_results: list[dict[str, Any]] = field(default_factory=list)
    policy_decision: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, **values: Any) -> "AzureDevOpsActionPack":
        return cls(pack_id=values.pop("pack_id", "") or f"ado-action-pack-{uuid4().hex}", **values)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AzureDevOpsActionPack":
        snake = {
            "pack_id": value.get("packId"), "source_entities": value.get("sourceEntities", []),
            "proposed_actions": value.get("proposedActions", []), "dry_run": value.get("dryRun", {}),
            "required_permissions": value.get("requiredPermissions", []), "approval_status": value.get("approvalStatus"),
            "expires_at": value.get("expiresAt"), "source_revisions": value.get("sourceRevisions", {}),
            "correlation_id": value.get("correlationId"), "run_id": value.get("runId", ""),
            "project_id": value.get("projectId", ""), "connection_id": value.get("connectionId", ""),
            "created_at": value.get("createdAt", ""), "updated_at": value.get("updatedAt", ""),
            "approved_by": value.get("approvedBy", ""), "approved_at": value.get("approvedAt", ""),
            "rejected_by": value.get("rejectedBy", ""), "rejected_at": value.get("rejectedAt", ""),
            "applied_by": value.get("appliedBy", ""), "applied_at": value.get("appliedAt", ""),
            "application_results": value.get("applicationResults", []), "policy_decision": value.get("policyDecision", {}),
        }
        return cls(trigger=str(value.get("trigger") or ""), risks=list(value.get("risks") or []), warnings=list(value.get("warnings") or []), **snake)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        aliases = {
            "pack_id": "packId", "source_entities": "sourceEntities", "proposed_actions": "proposedActions",
            "dry_run": "dryRun", "required_permissions": "requiredPermissions", "approval_status": "approvalStatus",
            "expires_at": "expiresAt", "source_revisions": "sourceRevisions", "correlation_id": "correlationId",
            "run_id": "runId", "project_id": "projectId", "connection_id": "connectionId",
            "created_at": "createdAt", "updated_at": "updatedAt", "approved_by": "approvedBy",
            "approved_at": "approvedAt", "rejected_by": "rejectedBy", "rejected_at": "rejectedAt",
            "applied_by": "appliedBy", "applied_at": "appliedAt", "application_results": "applicationResults",
            "policy_decision": "policyDecision",
        }
        return {aliases.get(key, key): item for key, item in value.items()}
