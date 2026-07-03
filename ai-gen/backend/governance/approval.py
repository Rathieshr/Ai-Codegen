"""Governance approval tracking."""

from __future__ import annotations

from typing import Any

from .types import normalize_approval, now_iso


class ApprovalEngine:
    def request(self, approvals: list[dict[str, Any]], approval: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_approval(approval)
        approvals.append(normalized)
        return normalized

    def transition(self, approvals: list[dict[str, Any]], approval_id: str, status: str, actor: str = "", reason: str = "") -> dict[str, Any]:
        for index, approval in enumerate(approvals):
            if approval.get("id") == approval_id:
                next_approval = normalize_approval({
                    **approval,
                    "status": status,
                    "approvedBy": actor or approval.get("approvedBy"),
                    "reason": reason or approval.get("reason"),
                    "updatedAt": now_iso(),
                })
                approvals[index] = next_approval
                return next_approval
        raise ValueError(f"Approval {approval_id} was not found.")

    def summary(self, approvals: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = {"Pending": 0, "Approved": 0, "Rejected": 0, "Expired": 0}
        for approval in approvals:
            status = str(approval.get("status") or "Pending")
            counts[status] = counts.get(status, 0) + 1
        return {"approvals": approvals, "count": len(approvals), "byStatus": counts}
