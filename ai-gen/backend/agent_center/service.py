"""Operational read model for HEI agents, workflows, jobs, and runtime runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


class AgentCenterError(RuntimeError):
    def __init__(self, message: str, *, code: str = "agent_center_error", status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


ADDITIONAL_AGENTS = (
    {
        "id": "validation",
        "name": "Validation Agent",
        "responsibility": "Evaluates implementation alignment and prepares validation findings for human review.",
        "triggers": ["Implementation Completed", "Validation Requested"],
        "actions": ["Validate Acceptance Coverage", "Validate Scope", "Validate Standards", "Prepare Findings"],
        "checkpoint": "Review Validation Findings",
        "featureFlag": "validationAgent",
    },
    {
        "id": "ado",
        "name": "ADO Agent",
        "responsibility": "Prepares Azure DevOps intelligence and approved automation action packs.",
        "triggers": ["Work Item Changed", "PR Created", "Build Failed", "Scheduled Reconciliation"],
        "actions": ["Prepare Intelligence", "Prepare Action Pack", "Wait For Approval"],
        "checkpoint": "Approve Azure DevOps Action Pack",
        "featureFlag": "adoAgent",
    },
)

AGENT_ALIASES = {
    "azure-devops-agent": "ado", "ado-agent": "ado", "ado": "ado",
    "planning-agent": "planning", "repository-agent": "repository", "execution-agent": "execution",
    "validation-agent": "validation", "qa-agent": "qa", "memory-agent": "memory", "review-agent": "review",
}


class AgentCenterService:
    """Builds a stable, read-mostly view without changing agent execution policy."""

    def __init__(self, *, orchestrator: Any, platform: Any, ado_agent: Any | None = None) -> None:
        self.orchestrator = orchestrator
        self.platform = platform
        self.ado_agent = ado_agent

    def list(self) -> dict[str, Any]:
        snapshot = self._snapshot()
        agents = [self._project_agent(definition, snapshot) for definition in snapshot["definitions"]]
        statuses: dict[str, int] = {}
        for agent in agents:
            statuses[agent["status"]] = statuses.get(agent["status"], 0) + 1
        return {
            "schemaVersion": "hei-agent-center-v1",
            "agents": agents,
            "summary": {
                "total": len(agents), "enabled": sum(agent["enabled"] for agent in agents),
                "running": statuses.get("Running", 0), "queued": statuses.get("Queued", 0),
                "failed": statuses.get("Failed", 0), "disabled": statuses.get("Disabled", 0),
                "pendingJobs": sum(agent["queue"] for agent in agents),
                "totalJobs": sum(agent["jobCount"] for agent in agents),
            },
            "statuses": statuses,
            "policyMode": "prepare_only",
            "generatedAt": _now(),
        }

    def get(self, agent_id: str) -> dict[str, Any]:
        snapshot = self._snapshot()
        definition = self._definition(snapshot, agent_id)
        agent = self._project_agent(definition, snapshot)
        agent["jobs"] = self._agent_jobs(agent["agentId"], snapshot)[:100]
        agent["runtimeRuns"] = self._agent_runs(agent["agentId"], snapshot)[:100]
        agent["logs"] = self._agent_logs(agent, snapshot["activity"])
        agent["diagnostics"] = {
            "workflowCount": len([item for item in snapshot["workflows"] if self._workflow_agent(item) == agent["agentId"]]),
            "platformJobCount": len([item for item in snapshot["platformJobs"] if self._job_agent(item) == agent["agentId"]]),
            "runtimeRunCount": len(self._agent_runs(agent["agentId"], snapshot)),
            "featureFlag": agent["featureFlag"], "policyMode": "prepare_only",
        }
        return agent

    def jobs(self, agent_id: str, *, status: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        snapshot = self._snapshot()
        definition = self._definition(snapshot, agent_id)
        normalized_id = _text(definition["id"])
        jobs = self._agent_jobs(normalized_id, snapshot)
        if status:
            jobs = [item for item in jobs if item["status"].casefold() == status.casefold()]
        safe_offset, safe_limit = max(0, offset), min(250, max(1, limit))
        page = jobs[safe_offset:safe_offset + safe_limit]
        return {
            "schemaVersion": "hei-agent-center-v1", "agentId": normalized_id, "jobs": page,
            "pagination": {"total": len(jobs), "offset": safe_offset, "limit": safe_limit, "returned": len(page), "hasMore": safe_offset + len(page) < len(jobs)},
            "generatedAt": _now(),
        }

    def health(self, agent_id: str) -> dict[str, Any]:
        agent = self.get(agent_id)
        return {
            "schemaVersion": "hei-agent-center-v1", "agentId": agent["agentId"], "name": agent["name"],
            "status": agent["status"], "health": agent["health"], "enabled": agent["enabled"],
            "queue": agent["queue"], "failures": agent["failures"], "successRate": agent["successRate"],
            "averageDurationMs": agent["averageDurationMs"], "lastRun": agent["lastRun"],
            "nextRun": agent["nextRun"], "warnings": agent["warnings"], "checkedAt": _now(),
        }

    def retry(self, job_id: str) -> dict[str, Any]:
        dashboard = self.orchestrator.dashboard()
        workflow = next((item for item in self._workflows(dashboard) if _text(item.get("id")) == job_id), None)
        if workflow:
            if _text(workflow.get("state")) != "Failed":
                raise AgentCenterError("Only failed agent workflows can be retried.", code="job_not_failed", status=409)
            return {"sourceType": "Workflow", **self.orchestrator.retry(job_id)}
        job = self.platform.jobs.get(job_id)
        if job:
            if _text(job.get("status")) != "Failed":
                raise AgentCenterError("Only failed platform jobs can be retried.", code="job_not_failed", status=409)
            return {"sourceType": "PlatformJob", **self.platform.job_runner.run_job(job_id)}
        raise AgentCenterError(f"Agent job '{job_id}' was not found.", code="job_not_found", status=404)

    def _snapshot(self) -> dict[str, Any]:
        dashboard = self.orchestrator.dashboard()
        definitions = [dict(item) for item in dashboard.get("agents") or [] if isinstance(item, dict)]
        known = {_text(item.get("id")) for item in definitions}
        definitions.extend(dict(item) for item in ADDITIONAL_AGENTS if item["id"] not in known)
        platform_jobs = list((self.platform.jobs.list_recent(1000) or {}).get("jobs") or [])
        platform_runs = list((self.platform.agent_runs.list_recent(1000) or {}).get("runs") or [])
        ado_runs = list((self.ado_agent.list_runs() or {}).get("runs") or []) if self.ado_agent else []
        run_ids = {_text(item.get("runId")) for item in platform_runs}
        platform_runs.extend(item for item in ado_runs if _text(item.get("runId")) not in run_ids)
        activity = list((self.platform.activity.list_recent(limit=500) or {}).get("activity") or [])
        return {
            "dashboard": dashboard, "definitions": definitions, "workflows": self._workflows(dashboard),
            "platformJobs": platform_jobs, "platformRuns": platform_runs, "activity": activity,
            "featureFlags": dict(dashboard.get("featureFlags") or {}),
        }

    @staticmethod
    def _workflows(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
        groups = ("runningAgents", "waitingAgents", "completedWorkflows", "failedWorkflows")
        values: dict[str, dict[str, Any]] = {}
        for group in groups:
            for item in dashboard.get(group) or []:
                if isinstance(item, dict) and item.get("id"):
                    values[_text(item["id"])] = dict(item)
        return list(values.values())

    def _definition(self, snapshot: dict[str, Any], agent_id: str) -> dict[str, Any]:
        normalized = self._normalize_agent_id(agent_id)
        definition = next((item for item in snapshot["definitions"] if self._normalize_agent_id(item.get("id")) == normalized), None)
        if not definition:
            raise AgentCenterError(f"Agent '{agent_id}' was not found.", code="agent_not_found", status=404)
        return definition

    def _project_agent(self, definition: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
        agent_id = self._normalize_agent_id(definition.get("id"))
        feature_flag = _text(definition.get("featureFlag")) or f"{agent_id}Agent"
        enabled = snapshot["featureFlags"].get(feature_flag, True) is not False
        jobs = self._agent_jobs(agent_id, snapshot)
        runs = self._agent_runs(agent_id, snapshot)
        queue = sum(item["status"] in {"Queued", "Pending", "WaitingApproval", "NeedsApproval"} for item in jobs)
        failures = sum(item["status"] == "Failed" for item in jobs) + sum(item["status"] == "Failed" for item in runs)
        running = any(item["status"] == "Running" for item in [*jobs, *runs])
        queued = any(item["status"] in {"Queued", "Pending", "WaitingApproval", "NeedsApproval"} for item in jobs)
        latest = self._latest([*jobs, *runs])
        status = "Disabled" if not enabled else "Running" if running else "Queued" if queued else "Failed" if latest and latest["status"] == "Failed" else "Idle"
        terminal = [item for item in [*jobs, *runs] if item["status"] in {"Completed", "Failed"}]
        completed = sum(item["status"] == "Completed" for item in terminal)
        success_rate = round((completed / len(terminal)) * 100, 1) if terminal else None
        durations = [float(item["durationMs"]) for item in [*jobs, *runs] if item.get("durationMs") is not None]
        average_duration = round(sum(durations) / len(durations), 2) if durations else 0.0
        health = "Disabled" if not enabled else "Failed" if status == "Failed" else "Degraded" if failures and success_rate is not None and success_rate < 80 else "Healthy"
        warnings = []
        if not enabled: warnings.append("Agent is disabled by feature flag.")
        if failures: warnings.append(f"{failures} failed job or runtime run{'s' if failures != 1 else ''} recorded.")
        return {
            "agentId": agent_id, "name": _text(definition.get("name")) or f"{agent_id.title()} Agent",
            "responsibility": _text(definition.get("responsibility")), "enabled": enabled,
            "featureFlag": feature_flag, "status": status, "health": health, "queue": queue,
            "jobCount": len(jobs), "runtimeCount": len(runs), "failures": failures,
            "successRate": success_rate, "averageDurationMs": average_duration,
            "lastRun": self._last_run(latest), "nextRun": _text(definition.get("nextRun")),
            "triggers": list(definition.get("triggers") or []), "actions": list(definition.get("actions") or []),
            "checkpoint": _text(definition.get("checkpoint")), "warnings": warnings,
        }

    def _agent_jobs(self, agent_id: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        workflows = [self._normalize_workflow(item) for item in snapshot["workflows"] if self._workflow_agent(item) == agent_id]
        platform = [self._normalize_job(item) for item in snapshot["platformJobs"] if self._job_agent(item) == agent_id]
        return sorted([*workflows, *platform], key=self._sort_time, reverse=True)

    def _agent_runs(self, agent_id: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return sorted([self._normalize_run(item) for item in snapshot["platformRuns"] if self._run_agent(item) == agent_id], key=self._sort_time, reverse=True)

    def _agent_logs(self, agent: dict[str, Any], activity: list[dict[str, Any]]) -> list[dict[str, Any]]:
        names = {agent["agentId"].casefold(), agent["name"].casefold()}
        return [item for item in activity if any(name in f"{item.get('title', '')} {item.get('description', '')} {item.get('metadata', {})}".casefold() for name in names)][:100]

    def _workflow_agent(self, item: dict[str, Any]) -> str:
        return self._normalize_agent_id(item.get("agentId") or item.get("agent"))

    def _job_agent(self, item: dict[str, Any]) -> str:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        return self._normalize_agent_id(payload.get("agentId") or item.get("agentId") or item.get("jobType"))

    def _run_agent(self, item: dict[str, Any]) -> str:
        return self._normalize_agent_id(item.get("agentId"))

    @staticmethod
    def _normalize_agent_id(value: Any) -> str:
        text = _text(value).casefold().replace("_", "-").replace(" ", "-")
        if text in AGENT_ALIASES: return AGENT_ALIASES[text]
        for name in ("planning", "repository", "execution", "validation", "qa", "memory", "review"):
            if name in text: return name
        if "azure" in text or "devops" in text: return "ado"
        return text.removesuffix("-agent")

    @staticmethod
    def _normalize_workflow(item: dict[str, Any]) -> dict[str, Any]:
        timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
        return {
            "jobId": _text(item.get("id")), "sourceType": "Workflow", "title": _text(item.get("trigger")) or "Agent workflow",
            "status": _text(item.get("state")) or "Unknown", "currentStep": _text(item.get("currentAction")),
            "nextAction": _text(item.get("nextAction")), "createdAt": _text(timeline[0].get("time") if timeline else ""),
            "completedAt": _text(timeline[-1].get("time") if timeline and item.get("state") in {"Completed", "Failed"} else ""),
            "durationMs": item.get("durationMs"), "retryCount": int(item.get("retryCount") or 0),
            "error": "; ".join(str(value) for value in item.get("errors") or []), "retryable": item.get("state") == "Failed",
            "correlationId": _text((item.get("context") or {}).get("correlationId") if isinstance(item.get("context"), dict) else ""),
        }

    @staticmethod
    def _normalize_job(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "jobId": _text(item.get("jobId")), "sourceType": "PlatformJob", "title": _text(item.get("jobType")) or "Platform job",
            "status": _text(item.get("status")) or "Unknown", "currentStep": _text((item.get("progress") or {}).get("currentStep") if isinstance(item.get("progress"), dict) else ""),
            "nextAction": "Retry failed job" if item.get("status") == "Failed" else "",
            "createdAt": _text(item.get("createdAt")), "completedAt": _text(item.get("completedAt") or item.get("failedAt")),
            "durationMs": _duration(item.get("startedAt"), item.get("completedAt") or item.get("failedAt")),
            "retryCount": int(item.get("retryCount") or 0), "error": _text(item.get("error")),
            "retryable": item.get("status") == "Failed", "correlationId": _text(item.get("correlationId")),
        }

    @staticmethod
    def _normalize_run(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "runId": _text(item.get("runId")), "status": _text(item.get("status")) or "Unknown",
            "startedAt": _text(item.get("startedAt")), "completedAt": _text(item.get("completedAt") or item.get("failedAt")),
            "durationMs": _duration(item.get("startedAt"), item.get("completedAt") or item.get("failedAt")),
            "error": _text(item.get("error")), "correlationId": _text(item.get("correlationId")),
        }

    @staticmethod
    def _sort_time(item: dict[str, Any]) -> str:
        return _text(item.get("completedAt") or item.get("createdAt") or item.get("startedAt"))

    def _latest(self, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        return sorted(items, key=self._sort_time, reverse=True)[0] if items else None

    @staticmethod
    def _last_run(item: dict[str, Any] | None) -> dict[str, Any]:
        if not item: return {"status": "NeverRun", "at": "", "id": ""}
        return {"status": item.get("status"), "at": item.get("completedAt") or item.get("createdAt") or item.get("startedAt") or "", "id": item.get("jobId") or item.get("runId") or ""}


def _duration(start: Any, end: Any) -> float | None:
    if not start or not end: return None
    try:
        first = datetime.fromisoformat(_text(start).replace("Z", "+00:00"))
        second = datetime.fromisoformat(_text(end).replace("Z", "+00:00"))
        return round(max(0.0, (second - first).total_seconds() * 1000), 2)
    except ValueError:
        return None
