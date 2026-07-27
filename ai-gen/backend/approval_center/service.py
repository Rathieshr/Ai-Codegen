"""Unified approval projection over the services that own each artifact lifecycle."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable


class ApprovalNotFoundError(LookupError):
    pass


class ApprovalPermissionError(PermissionError):
    pass


class ApprovalConflictError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _values(value: Any, key: str = "") -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and key and isinstance(value.get(key), list):
        return [dict(item) for item in value[key] if isinstance(item, dict)]
    if isinstance(value, dict):
        return [dict(item) for item in value.values() if isinstance(item, dict)]
    return []


class ApprovalCenterService:
    """Presents one queue while delegating decisions to the original owner."""

    def __init__(
        self,
        *,
        planning_provider: Callable[[], Any] = lambda: [],
        planning_approve: Callable[[str, str], Any] | None = None,
        planning_reject: Callable[[str, str], Any] | None = None,
        engineering_review_provider: Callable[[], Any] = lambda: [],
        engineering_review_decide: Callable[[str, dict[str, Any]], Any] | None = None,
        execution_plan_provider: Callable[[], Any] = lambda: [],
        memory_provider: Callable[[], Any] = lambda: [],
        memory_approve: Callable[[str, str], Any] | None = None,
        memory_reject: Callable[[str, str, str], Any] | None = None,
        ado_pack_provider: Callable[[], Any] = lambda: [],
        ado_pack_approve: Callable[[str, str, str], Any] | None = None,
        ado_pack_reject: Callable[[str, str, str], Any] | None = None,
        pr_comment_provider: Callable[[], Any] = lambda: [],
        pr_comment_approve: Callable[[str, str, str], Any] | None = None,
        pr_comment_reject: Callable[[str, str, str], Any] | None = None,
        recommendation_provider: Callable[[], Any] = lambda: [],
        recommendation_approve: Callable[[str, str], Any] | None = None,
        recommendation_reject: Callable[[str, str], Any] | None = None,
        governance_provider: Callable[[], Any] = lambda: [],
        governance_request: Callable[[dict[str, Any], str], Any] | None = None,
        governance_update: Callable[[str, str, str, str], Any] | None = None,
        audit_provider: Callable[[str], Any] = lambda _artifact_id: {"events": []},
        audit_recorder: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.planning_provider, self.planning_approve, self.planning_reject = planning_provider, planning_approve, planning_reject
        self.engineering_review_provider, self.engineering_review_decide = engineering_review_provider, engineering_review_decide
        self.execution_plan_provider = execution_plan_provider
        self.memory_provider, self.memory_approve, self.memory_reject = memory_provider, memory_approve, memory_reject
        self.ado_pack_provider, self.ado_pack_approve, self.ado_pack_reject = ado_pack_provider, ado_pack_approve, ado_pack_reject
        self.pr_comment_provider, self.pr_comment_approve, self.pr_comment_reject = pr_comment_provider, pr_comment_approve, pr_comment_reject
        self.recommendation_provider, self.recommendation_approve, self.recommendation_reject = recommendation_provider, recommendation_approve, recommendation_reject
        self.governance_provider, self.governance_request, self.governance_update = governance_provider, governance_request, governance_update
        self.audit_provider, self.audit_recorder = audit_provider, audit_recorder

    def list(self, *, category: str = "", status: str = "", search: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        records = self._records()
        query = search.strip().casefold()
        filtered = [
            item for item in records
            if (not category or item["category"].casefold() == category.casefold())
            and (not status or item["status"].casefold() == status.casefold())
            and (not query or query in " ".join((item["title"], item["summary"], item["category"])).casefold())
        ]
        safe_offset, safe_limit = max(0, offset), min(250, max(1, limit))
        page = [{key: value for key, value in item.items() if key != "sourceData"} for item in filtered[safe_offset:safe_offset + safe_limit]]
        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for item in records:
            by_status[item["status"]] = by_status.get(item["status"], 0) + 1
            by_category[item["category"]] = by_category.get(item["category"], 0) + 1
        return {
            "schemaVersion": "hei-approval-center-v1", "summary": {"total": len(records), "byStatus": by_status, "byCategory": by_category},
            "approvals": page, "filters": {"categories": sorted(by_category), "statuses": sorted(by_status)},
            "pagination": {"total": len(filtered), "offset": safe_offset, "limit": safe_limit, "returned": len(page), "hasMore": safe_offset + len(page) < len(filtered)},
            "generatedAt": _now(),
        }

    def get(self, approval_id: str) -> dict[str, Any]:
        item = next((record for record in self._records() if record["id"] == approval_id), None)
        if not item:
            raise ApprovalNotFoundError(f"Approval {approval_id} was not found.")
        audit = self.audit_provider(item["sourceId"])
        events = (audit.get("events") or audit.get("timeline") or audit.get("auditTimeline") or []) if isinstance(audit, dict) else []
        return {**deepcopy(item), "audit": events}

    def approve(self, approval_id: str, actor: str, role: str, reason: str = "") -> dict[str, Any]:
        return self._decide(approval_id, "Approved", actor, role, reason)

    def reject(self, approval_id: str, actor: str, role: str, reason: str = "") -> dict[str, Any]:
        return self._decide(approval_id, "Rejected", actor, role, reason)

    def _decide(self, approval_id: str, decision: str, actor: str, role: str, reason: str) -> dict[str, Any]:
        self._assert_permission(actor, role)
        item = self.get(approval_id)
        if item["expired"]:
            raise ApprovalConflictError("Approval has expired and must be regenerated.")
        if item["status"] not in {"Pending", "NeedsReview", "Draft", "Prepared"}:
            raise ApprovalConflictError(f"Approval cannot be changed from status {item['status']}.")
        source_id, category = item["sourceId"], item["category"]
        if category == "Planning Packs":
            operation = self.planning_approve if decision == "Approved" else self.planning_reject
            result = self._call(operation, source_id, actor)
        elif category == "Engineering Reviews":
            current_stage = item.get("sourceData", {}).get("currentStage") or {}
            result = self._call(self.engineering_review_decide, source_id, {
                "decision": "Approve" if decision == "Approved" else "Reject",
                "actor": actor,
                "role": current_stage.get("role") or "Engineering Lead",
                "comments": reason or (
                    "Approved from Approval Center."
                    if decision == "Approved"
                    else "Rejected from Approval Center."
                ),
            })
        elif category == "Execution Plans":
            result = self._governance_decision(item, decision, actor, reason)
        elif category == "Memory Candidates":
            operation = self.memory_approve if decision == "Approved" else self.memory_reject
            result = self._call(operation, source_id, actor, reason) if decision == "Rejected" else self._call(operation, source_id, actor)
        elif category == "ADO Action Packs":
            operation = self.ado_pack_approve if decision == "Approved" else self.ado_pack_reject
            result = self._call(operation, source_id, actor, reason)
        elif category == "PR Comments":
            operation = self.pr_comment_approve if decision == "Approved" else self.pr_comment_reject
            result = self._call(operation, source_id, actor, reason)
        elif category == "Recommendations":
            operation = self.recommendation_approve if decision == "Approved" else self.recommendation_reject
            result = self._call(operation, source_id, actor)
        elif category == "Validation Exceptions":
            result = self._governance_decision(item, decision, actor, reason)
        else:
            raise ApprovalConflictError(f"Approval category {category} is not actionable.")
        if self.audit_recorder:
            self.audit_recorder({
                "who": actor, "what": f"Approval Center {decision.lower()}", "why": reason,
                "artifactType": category, "artifactId": source_id, "eventType": "ApprovalCenterDecision",
                "metadata": {"approvalId": approval_id, "sourceStatus": item["status"]},
            })
        return {"approval": {**item, "status": decision, "decidedBy": actor, "decisionReason": reason, "updatedAt": _now()}, "sourceResult": result}

    def _governance_decision(self, item: dict[str, Any], decision: str, actor: str, reason: str) -> Any:
        approval_id = _text(item.get("governanceApprovalId"))
        if not approval_id:
            if not self.governance_request:
                raise ApprovalConflictError("Governance approval service is unavailable.")
            created = self.governance_request({
                "artifactType": item["category"], "artifactId": item["sourceId"], "artifactTitle": item["title"], "status": "Pending"
            }, actor)
            approval_id = _text((created.get("approval") or {}).get("id") if isinstance(created, dict) else "")
        return self._call(self.governance_update, approval_id, decision, actor, reason)

    def _records(self) -> list[dict[str, Any]]:
        governance = _values(self.governance_provider(), "approvals")
        governance_by_artifact = {_text(item.get("artifactId")): item for item in governance if item.get("artifactId")}
        records: list[dict[str, Any]] = []
        planning = self.planning_provider()
        for item in _values(planning, "items"):
            if item.get("source") != "planning_artifact" or item.get("type") == "Recommendation":
                continue
            records.append(self._record("Planning Packs", _text(item.get("id")), _text(item.get("title")), item, item.get("approvalStatus") or item.get("status"), item.get("updatedAt")))
        for item in _values(self.engineering_review_provider(), "reviews"):
            source_id = _text(item.get("reviewId"))
            summary = item.get("proposalSummary") or {}
            records.append(self._record(
                "Engineering Reviews",
                source_id,
                _text(summary.get("title")) or "Planning Proposal Engineering Review",
                item,
                item.get("status"),
                item.get("updatedAt") or item.get("createdAt"),
                expires_at=item.get("expiresAt"),
            ))
        for item in _values(self.execution_plan_provider()):
            source_id = _text(item.get("manifestId") or item.get("planId") or item.get("id"))
            approval = governance_by_artifact.get(source_id, {})
            records.append(self._record("Execution Plans", source_id, _text(item.get("objective")) or "Execution Plan", item, approval.get("status") or "Pending", item.get("generatedAt"), governance_id=approval.get("id")))
        for item in _values(self.memory_provider(), "candidates"):
            records.append(self._record("Memory Candidates", _text(item.get("candidateId")), _text(item.get("title")) or _text(item.get("candidateType")) or "Memory Candidate", item, item.get("approvalStatus") or item.get("status"), item.get("createdAt"), expires_at=item.get("expiresAt")))
        for item in _values(self.ado_pack_provider(), "actionPacks"):
            records.append(self._record("ADO Action Packs", _text(item.get("packId")), _text(item.get("trigger")) or "Azure DevOps Action Pack", item, item.get("approvalStatus") or item.get("status"), item.get("createdAt"), expires_at=item.get("expiresAt")))
        for item in _values(self.pr_comment_provider()):
            records.append(self._record("PR Comments", _text(item.get("commentPreviewId")), f"PR #{_text(item.get('pullRequestId'))} comment", item, item.get("approvalStatus") or "PendingApproval", item.get("createdAt")))
        for item in _values(self.recommendation_provider()):
            proposed = item.get("proposedValue")
            title = _text(proposed.get("title") if isinstance(proposed, dict) else proposed) or _text(item.get("recommendationType")) or "Work Item Recommendation"
            records.append(self._record("Recommendations", _text(item.get("recommendationId")), title, item, item.get("status"), item.get("createdAt")))
        for item in governance:
            artifact_type = _text(item.get("artifactType"))
            if "validation" not in artifact_type.casefold() or not any(value in artifact_type.casefold() for value in ("exception", "waiver", "override")):
                continue
            records.append(self._record("Validation Exceptions", _text(item.get("artifactId")), _text(item.get("artifactTitle")) or "Validation Exception", item, item.get("status"), item.get("createdAt"), expires_at=item.get("expiresAt"), governance_id=item.get("id")))
        deduped = {item["id"]: item for item in records if item.get("sourceId")}
        return sorted(deduped.values(), key=lambda item: item.get("requestedAt", ""), reverse=True)

    def _record(self, category: str, source_id: str, title: str, data: dict[str, Any], status: Any, requested_at: Any, *, expires_at: Any = "", governance_id: Any = "") -> dict[str, Any]:
        normalized_status = self._status(status)
        expiry = _text(expires_at)
        expired = bool(expiry and self._expired(expiry))
        if expired and normalized_status in {"Pending", "NeedsReview", "Draft", "Prepared"}:
            normalized_status = "Expired"
        summary = _text(data.get("description") or data.get("summary") or data.get("reason") or data.get("content"))
        return {
            "id": f"{self._slug(category)}:{source_id}", "sourceId": source_id, "category": category,
            "title": title or category[:-1], "summary": summary[:320], "status": normalized_status,
            "requestedAt": _text(requested_at) or _now(), "expiresAt": expiry, "expired": expired,
            "requestedBy": _text(data.get("requestedBy") or data.get("createdBy") or data.get("triggeredBy")) or "HEI",
            "confidence": data.get("confidence"), "risk": data.get("risk") or data.get("risks") or [],
            "projectId": _text(data.get("projectId")), "correlationId": _text(data.get("correlationId") or (data.get("diagnostics") or {}).get("correlationId") if isinstance(data.get("diagnostics"), dict) else ""),
            "governanceApprovalId": _text(governance_id), "canApprove": normalized_status in {"Pending", "NeedsReview", "Draft", "Prepared"},
            "canReject": normalized_status in {"Pending", "NeedsReview", "Draft", "Prepared"}, "sourceData": deepcopy(data),
        }

    @staticmethod
    def _status(value: Any) -> str:
        raw = _text(value).replace("_", "").replace(" ", "").casefold()
        return {
            "pendingapproval": "Pending", "pending": "Pending", "draft": "Draft", "needsreview": "NeedsReview",
            "pendingreview": "NeedsReview", "inreview": "NeedsReview", "changesrequested": "NeedsReview",
            "prepared": "Prepared", "approved": "Approved", "ready": "Approved", "rejected": "Rejected",
            "archived": "Rejected", "expired": "Expired", "stale": "Expired", "superseded": "Expired",
            "applied": "Approved",
        }.get(raw, _text(value) or "Pending")

    @staticmethod
    def _expired(value: str) -> bool:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except ValueError:
            return False

    @staticmethod
    def _slug(category: str) -> str:
        return category.casefold().replace(" ", "-")

    @staticmethod
    def _assert_permission(actor: str, role: str) -> None:
        if not actor.strip():
            raise ApprovalPermissionError("An authenticated approval actor is required.")
        normalized = role.strip().casefold().replace("_", " ")
        if normalized in {"viewer", "ai gen viewer", "reader", "readers"}:
            raise ApprovalPermissionError("Viewer access is read-only and cannot approve or reject engineering artifacts.")
        if normalized not in {"admin", "ai gen admin", "contributor", "ai gen contributor"}:
            raise ApprovalPermissionError("Current user role is not permitted to make approval decisions.")

    @staticmethod
    def _call(operation: Callable[..., Any] | None, *args: Any) -> Any:
        if not operation:
            raise ApprovalConflictError("The source approval operation is unavailable.")
        return operation(*args)
