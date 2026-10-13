"""Autonomous Engineering Agent engine."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .context import AgentContext
from .diagnostics import AgentDiagnostics
from .event_bus import AgentEventBus
from .history import AgentHistory
from .policy import AgentPolicy
from .registry import AgentRegistry
from .scheduler import AgentScheduler
from .types import now_iso
from .workflow import WorkflowEngine


class AgentEngine:
    def __init__(self, storage_path: Path | None = None, policy_path: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._path = storage_path or data_dir / "project_intelligence" / "agent_orchestrator.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = AgentRegistry()
        self.events = AgentEventBus()
        self.context = AgentContext()
        self.policy = AgentPolicy(policy_path)
        self.workflow = WorkflowEngine()
        self.scheduler = AgentScheduler()
        self.history = AgentHistory()
        self.diagnostics = AgentDiagnostics()

    def dashboard(self) -> dict[str, Any]:
        state = self._read()
        agents = self.registry.list_agents()
        workflows = state["workflows"]
        events = state["events"]
        last_runs = self._last_runs(workflows)
        failures = self.scheduler.failed(workflows)
        waiting = self.scheduler.waiting(workflows)
        return {
            "agents": agents,
            "featureFlags": self.policy.feature_flags(),
            "policies": self.policy.policies(),
            "runningAgents": self.scheduler.running(workflows),
            "waitingAgents": waiting,
            "completedWorkflows": self.scheduler.completed(workflows),
            "failedWorkflows": failures,
            "pendingJobs": waiting,
            "upcomingActions": self._upcoming_actions(workflows),
            "history": self.history.build(workflows, events),
            "agentTimeline": self.history.build(workflows, events),
            "lastRun": last_runs,
            "failures": failures,
            "diagnostics": self.diagnostics.summarize(agents, workflows, events, self.policy.feature_flags()),
        }

    def trigger(self, event: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        state = self._read()
        normalized = self.events.publish(state["events"], event)
        agent = self.registry.resolve(normalized["eventType"])
        if not agent:
            self._write(state)
            return {
                "handled": False,
                "event": normalized,
                "message": f"No agent is registered for {normalized['eventType']}.",
                "dashboard": self.dashboard(),
            }
        policy_decision = self.policy.policy_decision(agent)
        if not policy_decision["allowed"]:
            blocked = {
                "handled": False,
                "event": normalized,
                "agent": agent,
                "message": policy_decision["reason"],
                "policy": policy_decision,
                "dashboard": self.dashboard(),
            }
            return blocked
        workflow = self.workflow.build(agent, normalized, self.context.normalize(context), policy_decision)
        workflow["durationMs"] = round((time.monotonic() - started) * 1000, 2)
        state["workflows"].append(workflow)
        self._write(state)
        return {
            "handled": True,
            "event": normalized,
            "agent": agent,
            "policy": policy_decision,
            "workflow": workflow,
            "dashboard": self.dashboard(),
        }

    def resume(self, workflow_id: str, actor: str = "") -> dict[str, Any]:
        state = self._read()
        for index, workflow in enumerate(state["workflows"]):
            if workflow.get("id") == workflow_id:
                state["workflows"][index] = self.workflow.resume(workflow, actor)
                self._write(state)
                return {"workflow": state["workflows"][index]}
        raise ValueError(f"Workflow {workflow_id} was not found.")

    def retry(self, workflow_id: str) -> dict[str, Any]:
        state = self._read()
        for index, workflow in enumerate(state["workflows"]):
            if workflow.get("id") == workflow_id:
                state["workflows"][index] = self.scheduler.retry(workflow)
                self._write(state)
                return {"workflow": state["workflows"][index]}
        raise ValueError(f"Workflow {workflow_id} was not found.")

    def list_workflows(self, state_filter: str = "") -> dict[str, Any]:
        workflows = self._read()["workflows"]
        filtered = [workflow for workflow in workflows if not state_filter or workflow.get("state") == state_filter]
        return {"workflows": filtered, "count": len(filtered)}

    def list_events(self, event_type: str = "") -> dict[str, Any]:
        return self.events.list_events(self._read()["events"], event_type)

    def update_feature_flags(self, flags: dict[str, Any]) -> dict[str, Any]:
        updated = self.policy.update_feature_flags(flags)
        return {"featureFlags": updated, "policies": self.policy.policies()}

    def diagnostics_summary(self) -> dict[str, Any]:
        state = self._read()
        return self.diagnostics.summarize(
            self.registry.list_agents(),
            state["workflows"],
            state["events"],
            self.policy.feature_flags(),
        )

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"schemaVersion": "agent-orchestrator-v2", "events": [], "workflows": []}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schemaVersion": "agent-orchestrator-v2", "events": [], "workflows": []}
        return {
            "schemaVersion": "agent-orchestrator-v2",
            "events": payload.get("events") if isinstance(payload.get("events"), list) else [],
            "workflows": payload.get("workflows") if isinstance(payload.get("workflows"), list) else [],
        }

    def _write(self, state: dict[str, Any]) -> None:
        self._path.write_text(json.dumps({**state, "updatedAt": now_iso()}, indent=2), encoding="utf-8")

    def _upcoming_actions(self, workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "workflowId": workflow.get("id"),
                "agent": workflow.get("agent"),
                "nextAction": workflow.get("nextAction"),
                "artifactType": workflow.get("artifactType"),
                "artifactId": workflow.get("artifactId"),
                "status": workflow.get("status"),
            }
            for workflow in workflows
            if workflow.get("state") == "WaitingApproval"
        ]

    def _last_runs(self, workflows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for workflow in workflows:
            agent = str(workflow.get("agentId") or "")
            if not agent:
                continue
            timeline = workflow.get("timeline", [])
            last_time = timeline[-1].get("time") if timeline else ""
            output[agent] = {
                "workflowId": workflow.get("id"),
                "artifactType": workflow.get("artifactType"),
                "artifactId": workflow.get("artifactId"),
                "state": workflow.get("state"),
                "status": workflow.get("status"),
                "time": last_time,
            }
        return output
