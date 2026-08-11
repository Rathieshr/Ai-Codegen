"""Repository Intelligence agent orchestration and monitoring."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.platform.events import EventBus
from backend.platform.jobs import InMemoryJobQueue, JobHandlerRegistry, JobRunner
from backend.platform.shared import OperationStatus, now_iso

from ..domain import Repository, RepositoryStatus


REPOSITORY_AGENT_JOB = "RepositoryIntelligenceScan"
SUPPORTED_TRIGGERS = {
    "RepositoryRegistration",
    "ManualScan",
    "GitPush",
    "PRCreated",
    "PRMerged",
    "NightlyHealthCheck",
}
EVENT_TRIGGER_MAP = {
    "RepositoryRegistered": "RepositoryRegistration",
    "RepositoryScanRequested": "ManualScan",
    "GitPush": "GitPush",
    "PullRequestCreated": "PRCreated",
    "PullRequestMerged": "PRMerged",
    "NightlyHealthCheck": "NightlyHealthCheck",
}


class RepositoryIntelligenceJobHandler:
    def __init__(
        self,
        *,
        repository_service: Any,
        scanner: Any,
        snapshot_service: Any,
        parser_service: Any,
        graph_service: Any,
        file_ranking_service: Any,
        event_bus: EventBus,
        markdown_service: Any | None = None,
        repository_content_provider: Callable[[Repository, str], str] | None = None,
    ) -> None:
        self.repository_service = repository_service
        self.scanner = scanner
        self.snapshot_service = snapshot_service
        self.parser_service = parser_service
        self.graph_service = graph_service
        self.file_ranking_service = file_ranking_service
        self.event_bus = event_bus
        self.markdown_service = markdown_service
        self.repository_content_provider = repository_content_provider

    def handle(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job.get("payload") or {})
        repository_id = str(payload.get("repositoryId") or "")
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            raise ValueError(f"Repository '{repository_id}' was not found.")

        scan = self.scanner.request_scan(
            repository_id,
            mode=str(payload.get("mode") or "Full"),
            requested_by=str(payload.get("requestedBy") or "Repository Intelligence Agent"),
            root_path=str(payload.get("rootPath") or ""),
            manual_paths=list(payload.get("manualPaths") or []),
        )
        completed_scan, snapshot = self.scanner.run_scan(repository, scan)
        if completed_scan.status != "Completed":
            raise RuntimeError(completed_scan.message or "Repository scan failed.")

        documentation_registry = self._index_repository_markdown(repository, snapshot, completed_scan)
        snapshot.metadata = {
            **dict(snapshot.metadata or {}),
            "documentationRegistry": documentation_registry,
        }
        self.snapshot_service.save_snapshot(snapshot)
        symbols = self.parser_service.parse_snapshot(repository, snapshot)
        self.parser_service.save_symbols(repository_id, snapshot.snapshot_id, symbols)
        graph = self.graph_service.build_foundation_graph(repository, snapshot, symbols)
        self.graph_service.save_graph(graph)

        # Ranking is query-specific; this refresh verifies that its graph/snapshot inputs are ready.
        ranking_probe = self.file_ranking_service.rank_files(
            repository,
            artifact_type="Repository",
            title=repository.name,
            description="Repository intelligence refresh",
            selected_modules=list(snapshot.modules or [])[:5],
            limit=5,
        )
        if repository.status != RepositoryStatus.ACTIVE:
            active = Repository.from_dict({**repository.to_dict(), "status": RepositoryStatus.ACTIVE.value})
            self.repository_service.update_repository(repository_id, active)

        result = {
            "repositoryId": repository_id,
            "trigger": payload.get("trigger"),
            "scan": completed_scan.to_dict(),
            "snapshot": snapshot.to_dict(),
            "parsedSymbolCount": len(symbols),
            "graphNodeCount": len(graph.nodes),
            "graphRelationshipCount": len(graph.relationships),
            "rankingRefreshCount": len(ranking_probe),
            "documentationRegistry": documentation_registry,
            "completedAt": now_iso(),
        }
        self.event_bus.publish(
            {
                "eventType": "RepositoryIntelligenceUpdated",
                "source": "Agent",
                "repositoryId": repository_id,
                "correlationId": job.get("correlationId"),
                "payload": result,
            }
        )
        return result

    def _index_repository_markdown(
        self,
        repository: Repository,
        snapshot: Any,
        scan: Any,
    ) -> dict[str, Any]:
        if not self.markdown_service:
            return {"status": "Unavailable", "documentsIndexed": 0, "sectionsIndexed": 0}
        files = [
            item for item in list((snapshot.metadata or {}).get("files") or [])
            if isinstance(item, dict)
            and str(item.get("path") or "").casefold().endswith((".md", ".markdown", ".mdx"))
        ]
        root_value = str(scan.root_path or repository.metadata.get("localPath") or "")
        root = Path(root_value).expanduser()
        root_resolved = root.resolve() if root.is_dir() else None
        documents: list[dict[str, Any]] = []
        unreadable = 0
        for item in files:
            path = str(item.get("path") or "").strip().lstrip("/")
            if not path:
                continue
            try:
                if root_resolved:
                    candidate = (root_resolved / path).resolve()
                    if root_resolved not in candidate.parents and candidate != root_resolved:
                        unreadable += 1
                        continue
                    content = candidate.read_text(encoding="utf-8", errors="replace")
                elif self.repository_content_provider:
                    content = self.repository_content_provider(repository, path)
                else:
                    unreadable += 1
                    continue
            except Exception:
                unreadable += 1
                continue
            if str(content).strip():
                documents.append({
                    "path": path,
                    "content": str(content),
                    "revision": snapshot.commit_id or str(snapshot.version),
                    "contentHash": item.get("contentHash"),
                })
        indexed = self.markdown_service.index_repository_documents(
            documents,
            repository_id=repository.repository_id,
            repository_name=repository.name,
            project_id=repository.project_id or str(repository.metadata.get("adoProject") or ""),
            revision=snapshot.commit_id or str(snapshot.version),
            ignored_count=unreadable,
            include_patterns=repository.metadata.get("markdownIncludePatterns"),
            exclude_patterns=repository.metadata.get("markdownExcludePatterns"),
        )
        registry = self.markdown_service.get_repository_registry(repository.repository_id)
        return {
            "status": "Available" if registry["documentsIndexed"] else "NoDocuments",
            "documentsDiscovered": len(files),
            "documentsIndexed": registry["documentsIndexed"],
            "sectionsIndexed": registry["sectionsIndexed"],
            "statementsIndexed": registry["statementsIndexed"],
            "sourceFiles": registry["sourceFiles"],
            "classifications": registry["classifications"],
            "ignoredFiles": indexed.get("ignoredFiles", 0),
            "indexedAt": registry["indexedAt"],
            "repositoryRevision": registry["repositoryRevision"],
        }


class RepositoryIntelligenceAgent:
    def __init__(self, storage_root: Path, handler: RepositoryIntelligenceJobHandler) -> None:
        self.queue = InMemoryJobQueue(storage_root / "repository_agent_jobs.json")
        self.event_bus = handler.event_bus
        registry = JobHandlerRegistry()
        registry.register(REPOSITORY_AGENT_JOB, handler)
        self.runner = JobRunner(self.queue, registry, event_bus=self.event_bus)
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self.event_bus.registry.subscribe("RepositoryIntelligenceUpdated", self)
        for event_type in EVENT_TRIGGER_MAP:
            self.event_bus.registry.subscribe(event_type, self)

    def handle(self, event: dict[str, Any]) -> None:
        trigger = EVENT_TRIGGER_MAP.get(str(event.get("eventType") or ""))
        repository_id = str(event.get("repositoryId") or "")
        if trigger and repository_id:
            payload = dict(event.get("payload") or {})
            self.trigger(
                repository_id,
                trigger=trigger,
                requested_by=str(payload.get("requestedBy") or event.get("source") or "Event"),
                root_path=str(payload.get("rootPath") or ""),
                manual_paths=list(payload.get("manualPaths") or []),
                max_retries=int(payload.get("maxRetries") or 2),
                run_immediately=bool(payload.get("runImmediately", False)),
            )
            return
        for subscriber in list(self._subscribers):
            subscriber(event)

    def subscribe(self, subscriber: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.append(subscriber)

    def trigger(
        self,
        repository_id: str,
        *,
        trigger: str,
        requested_by: str = "",
        root_path: str = "",
        manual_paths: list[str] | None = None,
        mode: str = "",
        max_retries: int = 2,
        run_immediately: bool = False,
    ) -> dict[str, Any]:
        if trigger not in SUPPORTED_TRIGGERS:
            raise ValueError(f"Unsupported Repository Intelligence trigger '{trigger}'.")
        mode = mode or self._scan_mode(trigger, manual_paths or [])
        if run_immediately:
            self._cancel_superseded_jobs(repository_id)
        job = self.queue.enqueue(
            {
                "jobType": REPOSITORY_AGENT_JOB,
                "source": "Agent" if trigger != "ManualScan" else "Manual",
                "maxRetries": max(0, int(max_retries)),
                "payload": {
                    "repositoryId": repository_id,
                    "trigger": trigger,
                    "mode": mode,
                    "requestedBy": requested_by,
                    "rootPath": root_path,
                    "manualPaths": list(manual_paths or []),
                },
                "progress": {
                    "currentStep": "Queued",
                    "completedSteps": [],
                    "pendingSteps": ["Scan", "Snapshot", "Graph", "Ranking", "Notify"],
                    "percentComplete": 0,
                },
            }
        )
        self.event_bus.publish(
            {
                "eventType": "RepositoryIntelligenceQueued",
                "source": "Agent",
                "repositoryId": repository_id,
                "correlationId": job.get("correlationId"),
                "payload": {"jobId": job["jobId"], "trigger": trigger, "mode": mode},
            }
        )
        return self.run_job(job["jobId"]) if run_immediately else job

    def _cancel_superseded_jobs(self, repository_id: str) -> None:
        for job in list(self.queue.list_recent(limit=500).get("jobs") or []):
            if (
                (job.get("payload") or {}).get("repositoryId") == repository_id
                and job.get("status") in {"Queued", "Pending"}
            ):
                self.queue.cancel(str(job.get("jobId") or ""))

    def run_job(self, job_id: str) -> dict[str, Any]:
        result = self.runner.run_job(job_id)
        job = dict((result.get("metadata") or {}).get("job") or self.queue.get(job_id) or {})
        if job.get("status") in {OperationStatus.QUEUED.value, OperationStatus.FAILED.value}:
            self.event_bus.publish(
                {
                    "eventType": "RepositoryIntelligenceRetryScheduled"
                    if job.get("status") == OperationStatus.QUEUED.value
                    else "RepositoryIntelligenceFailed",
                    "source": "Agent",
                    "repositoryId": (job.get("payload") or {}).get("repositoryId"),
                    "correlationId": job.get("correlationId"),
                    "payload": {
                        "jobId": job.get("jobId"),
                        "retryCount": job.get("retryCount"),
                        "maxRetries": job.get("maxRetries"),
                        "error": job.get("error"),
                    },
                }
            )
        return job

    def run_next(self) -> dict[str, Any]:
        result = self.runner.run_next()
        return dict((result.get("metadata") or {}).get("job") or result)

    def list_jobs(self, repository_id: str, limit: int = 50) -> dict[str, Any]:
        jobs = list(self.queue.list_recent(limit=max(limit, 1)).get("jobs") or [])
        filtered = [job for job in jobs if (job.get("payload") or {}).get("repositoryId") == repository_id]
        return {"repositoryId": repository_id, "jobs": filtered[:limit], "count": len(filtered)}

    def status(self, repository_id: str) -> dict[str, Any]:
        jobs = self.list_jobs(repository_id, limit=100)["jobs"]
        active = next(
            (job for job in jobs if job.get("status") in {"Queued", "Pending", "Running"}),
            None,
        )
        latest = jobs[0] if jobs else None
        failed = [job for job in jobs if job.get("status") == "Failed"]
        return {
            "repositoryId": repository_id,
            "status": "Running" if active and active.get("status") == "Running" else "Queued" if active else "Idle",
            "activeJob": active,
            "lastJob": latest,
            "pendingJobs": sum(1 for job in jobs if job.get("status") in {"Queued", "Pending"}),
            "failedJobs": len(failed),
            "subscriberCount": len(self._subscribers),
            "supportedTriggers": sorted(SUPPORTED_TRIGGERS),
        }

    @staticmethod
    def _scan_mode(trigger: str, manual_paths: list[str]) -> str:
        if trigger == "ManualScan" and manual_paths:
            return "Manual"
        if trigger in {"GitPush", "PRCreated", "PRMerged", "NightlyHealthCheck"}:
            return "Incremental"
        return "Full"


class RepositoryMonitoringService:
    def __init__(
        self,
        *,
        repository_service: Any,
        scanner: Any,
        snapshot_service: Any,
        graph_service: Any,
        agent: RepositoryIntelligenceAgent,
    ) -> None:
        self.repository_service = repository_service
        self.scanner = scanner
        self.snapshot_service = snapshot_service
        self.graph_service = graph_service
        self.agent = agent

    def dashboard(self, repository_id: str) -> dict[str, Any] | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        snapshot = self.snapshot_service.get_latest_snapshot(repository_id)
        scan = self.scanner.get_scan(repository_id)
        graph = self.graph_service.get_graph(repository_id)
        agent_status = self.agent.status(repository_id)
        scan_duration_ms = _duration_ms(scan.started_at, scan.completed_at) if scan else 0
        health = self._health(repository, scan, snapshot, agent_status)
        return {
            "repositoryId": repository_id,
            "repositoryName": repository.name,
            "repositoryStatus": repository.status.value,
            "currentSnapshot": snapshot.to_dict() if snapshot else None,
            "lastScan": scan.to_dict() if scan else None,
            "lastScanAt": (scan.completed_at or scan.started_at or scan.requested_at) if scan else "",
            "scanDurationMs": scan_duration_ms,
            "filesIndexed": snapshot.total_files if snapshot else 0,
            "modulesIndexed": len(snapshot.modules) if snapshot else 0,
            "graphNodesIndexed": len(graph.nodes) if graph else 0,
            "pendingScan": agent_status["pendingJobs"] > 0,
            "pendingScanCount": agent_status["pendingJobs"],
            "health": health,
            "agentStatus": agent_status,
        }

    def dashboard_summary(self) -> dict[str, Any]:
        repositories = self.repository_service.list_repositories()
        items = [self.dashboard(repository.repository_id) for repository in repositories]
        dashboards = [item for item in items if item]
        health_counts: dict[str, int] = {}
        for item in dashboards:
            health = str(item.get("health") or "Pending")
            health_counts[health] = health_counts.get(health, 0) + 1
        return {
            "repositoryCount": len(dashboards),
            "healthyCount": health_counts.get("Healthy", 0),
            "pendingCount": health_counts.get("Pending", 0) + health_counts.get("InProgress", 0),
            "unhealthyCount": health_counts.get("Unhealthy", 0),
            "disabledCount": health_counts.get("Disabled", 0),
            "filesIndexed": sum(int(item.get("filesIndexed") or 0) for item in dashboards),
            "modulesIndexed": sum(int(item.get("modulesIndexed") or 0) for item in dashboards),
            "pendingScanCount": sum(int(item.get("pendingScanCount") or 0) for item in dashboards),
            "health": "Unhealthy"
            if health_counts.get("Unhealthy", 0)
            else "InProgress"
            if any(item.get("pendingScan") for item in dashboards)
            else "Healthy"
            if dashboards and health_counts.get("Healthy", 0) == len(dashboards)
            else "Pending",
            "repositories": dashboards,
        }

    @staticmethod
    def _health(repository: Repository, scan: Any, snapshot: Any, agent_status: dict[str, Any]) -> str:
        if repository.status == RepositoryStatus.DISABLED:
            return "Disabled"
        if scan and scan.status == "Failed":
            return "Degraded" if snapshot else "Unhealthy"
        if agent_status.get("status") in {"Queued", "Running"}:
            return "InProgress"
        if snapshot and snapshot.status == "Completed":
            return "Healthy"
        return "Pending"


def _duration_ms(started_at: str, completed_at: str) -> int:
    if not started_at or not completed_at:
        return 0
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0, int((end - start).total_seconds() * 1000))
    except ValueError:
        return 0
