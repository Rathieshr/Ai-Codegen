"""Human-approval and prohibited-action policy for the Azure DevOps agent."""

from __future__ import annotations

from typing import Any


class AzureDevOpsAgentPolicy:
    FORBIDDEN = {"ApprovePullRequest", "MergePullRequest", "DeleteWorkItem", "DeploySoftware", "BypassRepositoryPolicy"}
    CONSEQUENTAL = {
        "ApplyPlanningPack", "ApplyRecommendation", "CreateWorkItem", "UpdateWorkItem", "ChangeWorkItemState",
        "ApplyEstimate", "PostPullRequestComment", "ChangeIteration", "AssignUser",
    }

    def __init__(self, policy_engine: Any, *, allow_informational_pr_comments: bool = False) -> None:
        self._policy_engine = policy_engine
        self.allow_informational_pr_comments = allow_informational_pr_comments

    def evaluate(self, pack: dict[str, Any], *, operation: str, actor: str = "") -> dict[str, Any]:
        governance = self._policy_engine.enforce(
            {"artifactType": "AzureDevOpsActionPack", "status": pack.get("approvalStatus")},
            {"operation": operation, "approvalStatus": pack.get("approvalStatus")},
        )
        violations = list(governance.get("violations") or [])
        actions = pack.get("proposedActions") or []
        forbidden = [str(action.get("operation") or "") for action in actions if str(action.get("operation") or "") in self.FORBIDDEN]
        if forbidden:
            violations.append({"policyId": "ado-agent-prohibited-actions", "severity": "Critical", "message": f"Prohibited Azure DevOps agent actions: {', '.join(forbidden)}."})
        if operation == "apply" and not actor:
            violations.append({"policyId": "ado-agent-actor-required", "severity": "High", "message": "An authenticated actor is required to apply an action pack."})
        return {
            "allowed": not violations,
            "status": "Passed" if not violations else "Blocked",
            "violations": violations,
            "warnings": list(governance.get("warnings") or []),
            "policiesEvaluated": int(governance.get("policiesEvaluated") or 0) + 2,
        }

    def requires_approval(self, operation: str) -> bool:
        if operation == "PostPullRequestComment" and self.allow_informational_pr_comments:
            return False
        return operation in self.CONSEQUENTAL
