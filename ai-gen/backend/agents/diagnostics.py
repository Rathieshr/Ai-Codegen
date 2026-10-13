"""Diagnostics for the HEI Agent Orchestrator."""

from __future__ import annotations

from typing import Any


class AgentDiagnostics:
    def summarize(
        self,
        agents: list[dict[str, Any]],
        workflows: list[dict[str, Any]],
        events: list[dict[str, Any]],
        feature_flags: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        by_agent: dict[str, int] = {}
        by_state: dict[str, int] = {}
        by_trigger: dict[str, int] = {}
        retries = 0
        durations: list[float] = []
        for workflow in workflows:
            by_agent[str(workflow.get("agent") or "Unknown Agent")] = by_agent.get(str(workflow.get("agent") or "Unknown Agent"), 0) + 1
            by_state[str(workflow.get("state") or "Unknown")] = by_state.get(str(workflow.get("state") or "Unknown"), 0) + 1
            by_trigger[str(workflow.get("trigger") or "Unknown Trigger")] = by_trigger.get(str(workflow.get("trigger") or "Unknown Trigger"), 0) + 1
            retries += int(workflow.get("retryCount") or 0)
            if workflow.get("durationMs") is not None:
                try:
                    durations.append(float(workflow.get("durationMs")))
                except (TypeError, ValueError):
                    pass
        avg_duration = round(sum(durations) / len(durations), 2) if durations else 0.0
        return {
            "agentCount": len(agents),
            "workflowCount": len(workflows),
            "eventCount": len(events),
            "byAgent": by_agent,
            "byState": by_state,
            "byTrigger": by_trigger,
            "waitingApprovals": by_state.get("WaitingApproval", 0),
            "failedWorkflows": by_state.get("Failed", 0),
            "retryCount": retries,
            "averageExecutionMs": avg_duration,
            "featureFlags": feature_flags or {},
            "policyMode": "prepare_only",
        }
