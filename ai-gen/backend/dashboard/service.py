"""Operational aggregation for the HEI Engineering Command Center."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _list(value: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        return []
    return [item for item in value[key] if isinstance(item, dict)]


def _status_count(items: list[dict[str, Any]], *statuses: str) -> int:
    allowed = {value.casefold() for value in statuses}
    return sum(1 for item in items if str(item.get("status") or item.get("state") or "").casefold() in allowed)


class DashboardService:
    """Creates a read-only operational projection from existing HEI services."""

    def __init__(
        self,
        *,
        platform: Any,
        profile_provider: Callable[[], dict[str, Any]],
        repository_service: Any | None = None,
        ado_sync: Any | None = None,
        sprint_service: Any | None = None,
        agent_service: Any | None = None,
        governance_service: Any | None = None,
        runtime_service: Any | None = None,
        memory_candidate_service: Any | None = None,
        artifact_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.platform = platform
        self.profile_provider = profile_provider
        self.repository_service = repository_service
        self.ado_sync = ado_sync
        self.sprint_service = sprint_service
        self.agent_service = agent_service
        self.governance_service = governance_service
        self.runtime_service = runtime_service
        self.memory_candidate_service = memory_candidate_service
        self.artifact_provider = artifact_provider

    def overview(self, project_id: str = "") -> dict[str, Any]:
        warnings: list[dict[str, str]] = []
        profile = self._safe("project", self.profile_provider, {}, warnings)
        resolved_project_id = str(project_id or profile.get("project_id") or profile.get("projectId") or "")
        repositories = self._safe(
            "repository",
            lambda: self.repository_service.get_repository_monitoring_dashboard(),
            _repository_empty(),
            warnings,
            available=self.repository_service is not None,
        )
        repositories = _bounded_repositories(repositories)
        sync = self._safe(
            "azureDevOps",
            lambda: self.ado_sync.status(resolved_project_id),
            _sync_empty(resolved_project_id),
            warnings,
            available=self.ado_sync is not None and bool(resolved_project_id),
        )
        ado_cache = self._ado_cache(resolved_project_id, warnings)
        sprint = _sprint_projection(self._current_sprint(resolved_project_id, ado_cache, warnings))
        agents = self._safe("agents", lambda: self.agent_service.dashboard(), {}, warnings, available=self.agent_service is not None)
        governance = self._safe("approvals", lambda: self.governance_service.dashboard(), {}, warnings, available=self.governance_service is not None)
        runtime = self._safe("runtime", lambda: self.runtime_service.list(limit=250), {"traces": [], "count": 0}, warnings, available=self.runtime_service is not None)
        candidates = self._safe(
            "memoryCandidates",
            lambda: self.memory_candidate_service.list(resolved_project_id),
            {"candidates": [], "count": 0},
            warnings,
            available=self.memory_candidate_service is not None,
        )
        artifacts = self._safe("artifacts", self.artifact_provider, {"artifacts": [], "count": 0}, warnings, available=self.artifact_provider is not None)
        notifications = self._safe("notifications", lambda: self.platform.notifications.list_recent(limit=20), {"notifications": [], "count": 0}, warnings)
        activity = self._safe("activity", lambda: self.platform.activity.list_recent(limit=30), {"activity": [], "count": 0}, warnings)
        health = self._safe("health", self.platform.platform_health, {}, warnings)
        jobs = self._safe("jobs", lambda: self.platform.jobs.list_recent(limit=250), {"jobs": [], "count": 0}, warnings)
        artifact_items = _list(artifacts, "artifacts")
        trace_items = _list(runtime, "traces")
        job_items = _list(jobs, "jobs")
        approval_items = _list(governance.get("approvals") if isinstance(governance, dict) else {}, "approvals")
        candidate_items = _list(candidates, "candidates")
        notification_items = _list(notifications, "notifications")
        activity_items = _list(activity, "activity")
        build_items = [item for item in (ado_cache.get("builds") or {}).values() if isinstance(item, dict)] if isinstance(ado_cache.get("builds"), dict) else []
        pr_items = [item for item in (ado_cache.get("pullRequests") or {}).values() if isinstance(item, dict)] if isinstance(ado_cache.get("pullRequests"), dict) else []

        planning = _artifact_summary(artifact_items, ("epic", "feature", "story", "task", "planning"))
        execution = _artifact_summary(artifact_items, ("execution", "implementation", "manifest", "prompt"))
        validation = _artifact_summary(artifact_items, ("validation",))
        qa = _artifact_summary(artifact_items, ("qa", "test suite", "test plan", "coverage"))
        pr_intelligence = _artifact_summary(artifact_items, ("pr review", "pull request"))
        pr_intelligence.update({"pullRequestCount": len(pr_items), "openCount": _open_pr_count(pr_items)})
        execution_queue = {
            "running": _status_count(trace_items, "Running", "InProgress") + _matching_jobs(job_items, "execution", "Running"),
            "queued": _matching_jobs(job_items, "execution", "Queued", "Pending"),
            "failed": _status_count(trace_items, "Failed") + _matching_jobs(job_items, "execution", "Failed"),
            "recent": trace_items[:8],
            "total": int(runtime.get("count") or len(trace_items)) if isinstance(runtime, dict) else len(trace_items),
        }
        pending_candidates = [item for item in candidate_items if str(item.get("approvalStatus") or item.get("status") or "Pending") == "Pending"]
        pending_approvals = [item for item in approval_items if str(item.get("status") or "Pending") == "Pending"]
        unread = [item for item in notification_items if not item.get("readAt")]
        build_status = _build_summary(build_items)
        agent_running = _list(agents, "runningAgents")
        agent_waiting = _list(agents, "waitingAgents")

        overview = {
            "schemaVersion": "hei-dashboard-overview-v1",
            "status": _overall_status(profile, repositories, warnings),
            "currentProject": {
                "projectId": resolved_project_id,
                "name": str(profile.get("project_name") or profile.get("projectName") or ""),
                "domain": str(profile.get("domain") or ""),
                "configured": bool(profile.get("project_name") or resolved_project_id),
            },
            "repositoryStatus": repositories,
            "repositorySync": sync,
            "currentSprint": sprint,
            "runningAgents": {"count": len(agent_running), "waiting": len(agent_waiting), "items": agent_running[:8]},
            "executionQueue": execution_queue,
            "pendingApprovals": {"count": len(pending_approvals), "items": pending_approvals[:8]},
            "validation": validation,
            "qa": qa,
            "prIntelligence": pr_intelligence,
            "memoryCandidates": {"count": len(candidate_items), "pending": len(pending_candidates), "items": pending_candidates[:8]},
            "notifications": {"count": int(notifications.get("count") or len(notification_items)), "unread": len(unread), "items": notification_items[:8]},
            "buildStatus": build_status,
            "planning": planning,
            "execution": execution,
            "azureDevOps": {"connected": bool((sync.get("latestSync") if isinstance(sync, dict) else None) or ado_cache), "sync": sync, "pullRequests": len(pr_items)},
            "runtime": {"total": execution_queue["total"], "running": execution_queue["running"], "failed": execution_queue["failed"]},
            "agents": {"registered": len(_list(agents, "agents")), "running": len(agent_running), "waiting": len(agent_waiting), "failed": len(_list(agents, "failedWorkflows"))},
            "health": {"status": _health_status(health, warnings), "services": health},
            "recentActivity": {"count": int(activity.get("count") or len(activity_items)), "items": activity_items[:10]},
            "warnings": warnings,
            "generatedAt": _now(),
        }
        overview["widgets"] = self._widgets(overview)
        return overview

    def widgets(self, project_id: str = "") -> dict[str, Any]:
        overview = self.overview(project_id)
        return {"widgets": overview["widgets"], "count": len(overview["widgets"]), "generatedAt": overview["generatedAt"]}

    def summary(self, project_id: str = "") -> dict[str, Any]:
        value = self.overview(project_id)
        return {
            "status": value["status"], "project": value["currentProject"],
            "repositories": int(value["repositoryStatus"].get("repositoryCount") or 0),
            "repositoryHealth": value["repositoryStatus"].get("health") or "Unavailable",
            "runningAgents": value["runningAgents"]["count"],
            "executionQueued": value["executionQueue"]["queued"],
            "pendingApprovals": value["pendingApprovals"]["count"],
            "memoryCandidates": value["memoryCandidates"]["pending"],
            "unreadNotifications": value["notifications"]["unread"],
            "buildStatus": value["buildStatus"]["status"],
            "warningCount": len(value["warnings"]), "generatedAt": value["generatedAt"],
        }

    def _ado_cache(self, project_id: str, warnings: list[dict[str, str]]) -> dict[str, Any]:
        if not self.ado_sync or not project_id:
            return {}
        return self._safe("azureDevOpsCache", lambda: self.ado_sync.cache.snapshot(project_id), {}, warnings)

    def _current_sprint(self, project_id: str, cache: dict[str, Any], warnings: list[dict[str, str]]) -> dict[str, Any]:
        if not project_id:
            warnings.append({"source": "sprint", "code": "not_configured", "message": "sprint is not configured for this project."})
            return _sprint_empty(project_id)
        iterations = cache.get("iterations") if isinstance(cache.get("iterations"), dict) else {}
        current = next(
            (
                item for item in iterations.values()
                if isinstance(item, dict) and str(item.get("timeFrame") or "").casefold() == "current"
            ),
            None,
        )
        if not current:
            return _sprint_empty(project_id)
        iteration_id = str(current.get("iterationId") or current.get("id") or "")
        repository = getattr(self.sprint_service, "repository", None) if self.sprint_service else None
        if repository and iteration_id:
            existing = self._safe("sprintReport", lambda: repository.get(project_id, iteration_id), None, warnings)
            if isinstance(existing, dict):
                return existing
        return {
            "projectId": project_id, "iterationId": iteration_id, "iteration": current,
            "status": "NotAnalyzed", "health": "NotAnalyzed",
            "message": "Sprint is synchronized. Run Sprint Intelligence for delivery health and forecast.",
        }

    def _safe(self, source: str, call: Callable[[], Any] | None, fallback: Any, warnings: list[dict[str, str]], *, available: bool = True) -> Any:
        if not available or call is None:
            warnings.append({"source": source, "code": "not_configured", "message": f"{source} is not configured for this project."})
            return fallback
        try:
            value = call()
            return value if value is not None else fallback
        except Exception as error:
            warnings.append({"source": source, "code": "unavailable", "message": str(error) or f"{source} is unavailable."})
            return fallback

    @staticmethod
    def _widgets(value: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            _widget("repository", "Repository", value["repositoryStatus"].get("health") or "Pending", value["repositoryStatus"].get("repositoryCount") or 0, "Registered repositories and synchronization health.", "repository"),
            _widget("planning", "Planning", value["planning"]["status"], value["planning"]["count"], "Current approved and draft planning artifacts.", "planning"),
            _widget("execution", "Execution", value["execution"]["status"], value["executionQueue"]["queued"] + value["executionQueue"]["running"], "Implementation packages and active execution work.", "execution"),
            _widget("azure-devops", "Azure DevOps", "Connected" if value["azureDevOps"]["connected"] else "Not Connected", value["azureDevOps"]["pullRequests"], "Synchronized engineering system-of-record state.", "azure-devops"),
            _widget("approvals", "Approvals", "Attention" if value["pendingApprovals"]["count"] else "Clear", value["pendingApprovals"]["count"], "Human decisions waiting for review.", "approvals"),
            _widget("runtime", "Runtime", "Attention" if value["runtime"]["failed"] else "Healthy", value["runtime"]["running"], "AI execution sessions and failures.", "execution"),
            _widget("agents", "Agents", "Running" if value["agents"]["running"] else "Idle", value["agents"]["running"], "Registered, running, and waiting engineering agents.", "agents"),
            _widget("health", "Health", value["health"]["status"], len(value["warnings"]), "Platform service health and degraded dependencies.", "health"),
            _widget("recent-activity", "Recent Activity", "Available" if value["recentActivity"]["count"] else "Empty", value["recentActivity"]["count"], "Latest lifecycle and platform activity.", "activity"),
        ]


def _repository_empty() -> dict[str, Any]:
    return {"repositoryCount": 0, "healthyCount": 0, "pendingCount": 0, "unhealthyCount": 0, "filesIndexed": 0, "modulesIndexed": 0, "pendingScanCount": 0, "health": "NotConfigured", "repositories": []}


def _bounded_repositories(value: Any) -> dict[str, Any]:
    result = dict(value) if isinstance(value, dict) else _repository_empty()
    items = result.get("repositories") if isinstance(result.get("repositories"), list) else []
    result["repositories"] = [item for item in items if isinstance(item, dict)][:50]
    return result


def _sync_empty(project_id: str) -> dict[str, Any]:
    return {"projectId": project_id, "latestSync": None, "collectionCounts": {}, "centralized": True, "sourceOfTruth": "Azure DevOps", "status": "NotConnected"}


def _sprint_empty(project_id: str) -> dict[str, Any]:
    return {"projectId": project_id, "status": "NotAvailable", "health": "NotAvailable", "message": "No current sprint is available."}


def _sprint_projection(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "projectId": source.get("projectId") or "", "iterationId": source.get("iterationId") or "",
        "iteration": source.get("iteration") if isinstance(source.get("iteration"), dict) else {},
        "status": source.get("status") or source.get("health") or "NotAvailable",
        "health": source.get("health") or source.get("status") or "NotAvailable",
        "completionConfidence": source.get("completionConfidence"),
        "forecast": source.get("forecast") if isinstance(source.get("forecast"), dict) else {},
        "metrics": source.get("metrics") if isinstance(source.get("metrics"), dict) else {},
        "currentBlockers": [item for item in (source.get("currentBlockers") or []) if isinstance(item, dict)][:8],
        "deliveryRisks": [item for item in (source.get("deliveryRisks") or []) if isinstance(item, dict)][:8],
        "message": source.get("message") or "",
        "generatedAt": source.get("generatedAt") or "",
    }


def _artifact_summary(items: list[dict[str, Any]], terms: tuple[str, ...]) -> dict[str, Any]:
    matches = [item for item in items if any(term in str(item.get("artifact_type") or item.get("artifactType") or "").casefold() for term in terms)]
    approved = sum(1 for item in matches if str(item.get("state") or item.get("status") or "").casefold() in {"approved", "locked", "passed", "ready"})
    status = "Ready" if matches and approved == len(matches) else "In Progress" if matches else "Not Started"
    return {"count": len(matches), "approved": approved, "pending": len(matches) - approved, "status": status, "items": matches[:8]}


def _matching_jobs(items: list[dict[str, Any]], term: str, *statuses: str) -> int:
    allowed = {status.casefold() for status in statuses}
    return sum(1 for item in items if term in str(item.get("jobType") or item.get("type") or "").casefold() and str(item.get("status") or "").casefold() in allowed)


def _open_pr_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if str(item.get("status") or "").casefold() not in {"completed", "abandoned", "merged", "closed"})


def _build_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    failed = sum(1 for item in items if str(item.get("result") or item.get("status") or "").casefold() in {"failed", "canceled", "cancelled", "partiallysucceeded"})
    running = sum(1 for item in items if str(item.get("status") or "").casefold() in {"running", "inprogress", "notstarted"})
    status = "Failed" if failed else "Running" if running else "Succeeded" if items else "Not Available"
    return {"status": status, "count": len(items), "failed": failed, "running": running, "items": items[:8]}


def _health_status(health: dict[str, Any], warnings: list[dict[str, str]]) -> str:
    values = [str(value).casefold() for value in health.values() if isinstance(value, str)]
    if any(value in {"failed", "unhealthy", "offline"} for value in values):
        return "Unhealthy"
    if warnings or any(value in {"degraded", "not_registered", "unavailable"} for value in values):
        return "Degraded"
    return "Healthy"


def _overall_status(profile: dict[str, Any], repositories: dict[str, Any], warnings: list[dict[str, str]]) -> str:
    if not (profile.get("project_name") or profile.get("projectName") or profile.get("project_id") or profile.get("projectId")) and not repositories.get("repositoryCount"):
        return "Empty"
    if any(item["code"] == "unavailable" for item in warnings):
        return "Offline"
    return "NeedsAttention" if warnings or repositories.get("health") in {"Pending", "Unhealthy", "Degraded"} else "Ready"


def _widget(widget_id: str, title: str, status: str, value: Any, summary: str, target: str) -> dict[str, Any]:
    return {"id": widget_id, "title": title, "status": status, "value": value, "summary": summary, "target": target}
