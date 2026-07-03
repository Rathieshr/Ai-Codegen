"""Agent workflow construction and approval checkpoints."""

from __future__ import annotations

from typing import Any

from .types import APPROVAL_CHECKPOINT, workflow_event, workflow_id


class WorkflowEngine:
    def build(self, agent: dict[str, Any], event: dict[str, Any], context: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
        policy = policy or {}
        workflow = {
            "id": workflow_id(),
            "agentId": agent["id"],
            "agent": agent["name"],
            "trigger": event["eventType"],
            "artifactType": event.get("artifactType", ""),
            "artifactId": event.get("artifactId", ""),
            "artifactTitle": event.get("artifactTitle", ""),
            "state": "WaitingApproval",
            "status": "Waiting",
            "currentAction": APPROVAL_CHECKPOINT,
            "nextAction": agent.get("checkpoint") or "Human Approval",
            "approvalRequired": policy.get("approvalRequired", True),
            "featureFlag": policy.get("featureFlag", ""),
            "policyDecision": policy,
            "steps": self._steps(agent),
            "timeline": [
                workflow_event(f"{agent['name']} triggered by {event['eventType']}", "Started", {"eventId": event["id"]}),
            ],
            "context": context,
            "retryCount": 0,
            "errors": [],
        }
        workflow["timeline"].append(workflow_event("Policy gate evaluated", "Completed", {"reason": policy.get("reason", ""), "featureFlag": policy.get("featureFlag", "")}))
        workflow["timeline"].extend(workflow_event(step["name"], step["status"]) for step in workflow["steps"])
        workflow["timeline"].append(workflow_event(APPROVAL_CHECKPOINT, "Waiting", {"nextAction": workflow["nextAction"]}))
        return workflow

    def resume(self, workflow: dict[str, Any], actor: str = "") -> dict[str, Any]:
        if workflow.get("state") != "WaitingApproval":
            workflow["timeline"].append(workflow_event("Manual resume ignored", "Skipped", {"reason": "workflow_not_waiting"}))
            return workflow
        workflow["state"] = "Completed"
        workflow["status"] = "Completed"
        workflow["currentAction"] = "Completed"
        workflow["nextAction"] = "No pending agent action"
        workflow["timeline"].append(workflow_event("Human approval received", "Completed", {"actor": actor or "user"}))
        return workflow

    def fail(self, workflow: dict[str, Any], error: str) -> dict[str, Any]:
        workflow["state"] = "Failed"
        workflow["status"] = "Failed"
        workflow["errors"] = [*workflow.get("errors", []), error]
        workflow["timeline"].append(workflow_event("Workflow failed", "Failed", {"error": error}))
        return workflow

    def _steps(self, agent: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"name": action, "status": "Prepared", "approvalBoundary": False}
            for action in agent.get("actions", [])
        ]
