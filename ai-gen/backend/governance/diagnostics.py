"""Governance diagnostics."""

from __future__ import annotations

from typing import Any


class GovernanceDiagnostics:
    def summarize(self, state: dict[str, Any]) -> dict[str, Any]:
        policies = state.get("policies") if isinstance(state.get("policies"), list) else []
        approvals = state.get("approvals") if isinstance(state.get("approvals"), list) else []
        metrics = state.get("metrics") if isinstance(state.get("metrics"), list) else []
        feedback = state.get("feedback") if isinstance(state.get("feedback"), list) else []
        observations = state.get("observability") if isinstance(state.get("observability"), list) else []
        audit = state.get("audit") if isinstance(state.get("audit"), list) else []
        return {
            "policyCount": len(policies),
            "approvalCount": len(approvals),
            "metricCount": len(metrics),
            "feedbackCount": len(feedback),
            "observationCount": len(observations),
            "auditEventCount": len(audit),
            "enabledPolicies": len([policy for policy in policies if policy.get("enabled", True)]),
            "pendingApprovals": len([approval for approval in approvals if approval.get("status") == "Pending"]),
        }
