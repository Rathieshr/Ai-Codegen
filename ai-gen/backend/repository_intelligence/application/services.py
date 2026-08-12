"""Application orchestration for Repository Intelligence foundation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from ..domain import (
    IContextCapsuleBuilder,
    IFileRankingService,
    IEngineeringGraphService,
    IRepositoryParserService,
    IRepositoryScanner,
    IRepositoryService,
    ISnapshotService,
    Repository,
    RepositoryStatus,
)


@dataclass
class RepositoryIntelligenceApplicationService:
    repository_service: IRepositoryService
    scanner: IRepositoryScanner
    snapshot_service: ISnapshotService
    graph_service: IEngineeringGraphService
    parser_service: IRepositoryParserService
    file_ranking_service: IFileRankingService
    context_capsule_builder: IContextCapsuleBuilder
    agent: object
    monitoring_service: object
    repository_content_provider: Callable[[Repository, str], str] | None = None
    markdown_service: object | None = None

    def create_repository(self, payload: dict) -> dict:
        repository = Repository.from_dict(payload)
        self._validate_repository(repository)
        duplicate = self.repository_service.find_by_url(repository.url)
        if duplicate:
            raise ValueError(f"Repository URL is already registered as '{duplicate.name}'.")
        repository = self.repository_service.create_repository(repository)
        self.agent.trigger(
            repository.repository_id,
            trigger="RepositoryRegistration",
            requested_by=payload.get("requestedBy") or "",
        )
        return self._build_repository_response(repository)

    def update_repository(self, repository_id: str, payload: dict) -> dict | None:
        existing = self.repository_service.get_repository(repository_id)
        if not existing:
            return None
        merged = Repository.from_dict(
            {
                **existing.to_dict(),
                **payload,
                "repositoryId": repository_id,
                "createdAt": existing.created_at,
            }
        )
        self._validate_repository(merged)
        duplicate = self.repository_service.find_by_url(merged.url)
        if duplicate and duplicate.repository_id != repository_id:
            raise ValueError(f"Repository URL is already registered as '{duplicate.name}'.")
        updated = self.repository_service.update_repository(repository_id, merged)
        return self._build_repository_response(updated) if updated else None

    def list_repositories(self) -> dict:
        items = [self._build_repository_response(repository) for repository in self.repository_service.list_repositories()]
        return {"repositories": items, "count": len(items)}

    def get_repository(self, repository_id: str) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        return self._build_repository_response(repository)

    def get_repository_status(self, repository_id: str) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        status = self.repository_service.get_repository_status(repository_id) or {}
        graph = self.graph_service.get_graph_status(repository_id)
        scan = self.scanner.get_scan(repository_id)
        snapshot = self.snapshot_service.get_latest_snapshot(repository_id)
        documentation = dict((snapshot.metadata or {}).get("documentationRegistry") or {}) if snapshot else {}
        return {
            "repositoryId": repository.repository_id,
            "repositoryName": repository.name,
            "status": repository.status.value,
            "scanStatus": status.get("scanStatus") or (scan.status if scan else RepositoryStatus.PENDING_SCAN.value),
            "snapshotStatus": status.get("snapshotStatus") or ("Available" if snapshot else "NotAvailable"),
            "graphStatus": graph.get("status") or "NotConnected",
            "message": status.get("message")
            or "Repository Intelligence foundation is ready. Scanning will be added in a later phase.",
            "latestSnapshotId": snapshot.snapshot_id if snapshot else "",
            "latestScanId": scan.scan_id if scan else "",
            "scanMode": scan.mode if scan else "",
            "progress": dict(scan.progress) if scan else {},
            "documentationStatus": documentation.get("status") or "NotIndexed",
            "markdownDocumentsIndexed": int(documentation.get("documentsIndexed") or 0),
            "markdownSectionsIndexed": int(documentation.get("sectionsIndexed") or 0),
        }

    def get_current_snapshot(self, repository_id: str) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        snapshot = self.snapshot_service.get_latest_snapshot(repository_id)
        return snapshot.to_dict() if snapshot else None

    def list_markdown_documents(self, repository_id: str) -> list[dict]:
        """Read Markdown through the registered repository content boundary."""
        repository = self.repository_service.get_repository(repository_id)
        snapshot = self.snapshot_service.get_latest_snapshot(repository_id)
        if not repository or not snapshot:
            return []
        metadata = snapshot.metadata if isinstance(snapshot.metadata, dict) else {}
        files = [
            item for item in list(metadata.get("files") or [])
            if isinstance(item, dict)
            and str(item.get("path") or "").casefold().endswith((".md", ".markdown", ".mdx"))
        ]
        root = Path(str(repository.metadata.get("localPath") or "")).expanduser()
        documents = []
        for item in files:
            path = str(item.get("path") or "").strip().lstrip("/")
            if not path:
                continue
            try:
                if root.is_dir():
                    candidate = (root / path).resolve()
                    if root.resolve() not in candidate.parents and candidate != root.resolve():
                        continue
                    content = candidate.read_text(encoding="utf-8", errors="replace")
                elif self.repository_content_provider:
                    content = self.repository_content_provider(repository, path)
                else:
                    continue
            except Exception:
                continue
            if content:
                documents.append({
                    "path": path,
                    "content": str(content),
                    "revision": snapshot.commit_id or snapshot.version,
                    "contentHash": item.get("contentHash"),
                })
        return documents

    def get_markdown_registry(self, repository_id: str) -> dict | None:
        if not self.repository_service.get_repository(repository_id):
            return None
        if not self.markdown_service:
            return {
                "repositoryId": repository_id,
                "status": "Unavailable",
                "documentsIndexed": 0,
                "sectionsIndexed": 0,
                "sections": [],
            }
        registry = self.markdown_service.get_repository_registry(repository_id)
        return {
            **registry,
            "status": "Available" if registry.get("documentsIndexed") else "NoDocuments",
        }

    def list_snapshot_history(self, repository_id: str) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        snapshots = self.snapshot_service.list_snapshots(repository_id)
        return {
            "repositoryId": repository_id,
            "currentSnapshotId": snapshots[-1].snapshot_id if snapshots else "",
            "count": len(snapshots),
            "snapshots": [snapshot.to_dict() for snapshot in snapshots],
        }

    def compare_snapshots(self, repository_id: str, left_snapshot_id: str, right_snapshot_id: str) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        left = self.snapshot_service.get_snapshot(repository_id, left_snapshot_id)
        right = self.snapshot_service.get_snapshot(repository_id, right_snapshot_id)
        if not left or not right:
            raise ValueError("Both snapshots must exist for comparison.")
        left_languages = dict(left.languages or {})
        right_languages = dict(right.languages or {})
        left_modules = set(left.modules or [])
        right_modules = set(right.modules or [])
        return {
            "repositoryId": repository_id,
            "leftSnapshot": left.to_dict(),
            "rightSnapshot": right.to_dict(),
            "comparison": {
                "branchChanged": left.branch != right.branch,
                "commitChanged": left.commit_id != right.commit_id,
                "totalFilesDelta": right.total_files - left.total_files,
                "languageDelta": {
                    key: right_languages.get(key, 0) - left_languages.get(key, 0)
                    for key in sorted(set(left_languages) | set(right_languages))
                },
                "modulesAdded": sorted(right_modules - left_modules),
                "modulesRemoved": sorted(left_modules - right_modules),
                "statusChanged": left.status != right.status,
            },
        }

    def get_graph(self, repository_id: str) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        graph = self.graph_service.get_graph(repository_id)
        return graph.to_dict() if graph else None

    def query_graph_nodes(self, repository_id: str, *, node_type: str = "", search: str = "") -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        nodes = self.graph_service.query_nodes(repository_id, node_type=node_type, search=search)
        return {"repositoryId": repository_id, "count": len(nodes), "nodes": nodes}

    def query_graph_relationships(
        self,
        repository_id: str,
        *,
        relationship_type: str = "",
        from_node_id: str = "",
        to_node_id: str = "",
        search: str = "",
    ) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        relationships = self.graph_service.query_relationships(
            repository_id,
            relationship_type=relationship_type,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            search=search,
        )
        return {
            "repositoryId": repository_id,
            "count": len(relationships),
            "relationships": relationships,
        }

    def list_symbols(
        self,
        repository_id: str,
        *,
        snapshot_id: str = "",
        language: str = "",
        kind: str = "",
        path: str = "",
        search: str = "",
    ) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        symbols = self.parser_service.list_symbols(
            repository_id,
            snapshot_id=snapshot_id,
            language=language,
            kind=kind,
            path=path,
            search=search,
        )
        return {
            "repositoryId": repository_id,
            "count": len(symbols),
            "symbols": [symbol.to_dict() for symbol in symbols],
        }

    def rank_repository_files(
        self,
        repository_id: str,
        *,
        artifact_type: str,
        title: str,
        description: str = "",
        acceptance_criteria: list[str] | None = None,
        tags: list[str] | None = None,
        selected_modules: list[str] | None = None,
        selected_flows: list[str] | None = None,
        limit: int = 10,
    ) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        rankings = self.file_ranking_service.rank_files(
            repository,
            artifact_type=artifact_type,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria or [],
            tags=tags or [],
            selected_modules=selected_modules or [],
            selected_flows=selected_flows or [],
            limit=limit,
        )
        return {
            "repositoryId": repository_id,
            "artifactType": artifact_type,
            "title": title,
            "count": len(rankings),
            "files": [item.to_dict() for item in rankings],
        }

    def build_repository_context_capsule(
        self,
        repository_id: str,
        *,
        story: dict,
        selected_modules: list[str] | None = None,
        selected_flows: list[str] | None = None,
        limit: int = 8,
    ) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        snapshot = self.snapshot_service.get_latest_snapshot(repository_id)
        graph = self.graph_service.get_graph(repository_id)
        rankings = self.file_ranking_service.rank_files(
            repository,
            artifact_type=str(story.get("type") or story.get("work_item_type") or "Story"),
            title=str(story.get("title") or ""),
            description=str(story.get("description") or ""),
            acceptance_criteria=list(story.get("acceptance_criteria") or []),
            selected_modules=selected_modules or [],
            selected_flows=selected_flows or [],
            limit=limit,
        )
        capsule = self.context_capsule_builder.build_capsule(
            story=story,
            repository_snapshot=snapshot.to_dict() if snapshot else {},
            engineering_graph=graph.to_dict() if graph else {},
            repository_ranking=rankings,
            selected_modules=selected_modules or [],
            selected_flows=selected_flows or [],
        )
        return {
            "repositoryId": repository_id,
            "snapshotId": snapshot.snapshot_id if snapshot else "",
            "graphId": graph.graph_id if graph else "",
            "rankingCount": len(rankings),
            "capsule": capsule.to_dict(),
        }

    def delete_repository(self, repository_id: str) -> bool:
        return self.repository_service.delete_repository(repository_id)

    def scan_repository(
        self,
        repository_id: str,
        *,
        mode: str = "Full",
        requested_by: str = "",
        root_path: str = "",
        manual_paths: list[str] | None = None,
    ) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        trigger = "ManualScan"
        job = self.agent.trigger(
            repository_id,
            trigger=trigger,
            requested_by=requested_by,
            root_path=root_path,
            manual_paths=manual_paths,
            mode=mode,
            run_immediately=True,
        )
        if job.get("status") != "Completed":
            failed_scan = self.scanner.get_scan(repository_id)
            return {
                "scan": failed_scan.to_dict() if failed_scan else {"status": "Failed", "message": job.get("error")},
                "snapshot": {},
                "parsedSymbolCount": 0,
                "agentJob": job,
            }
        return dict(job.get("result") or {})

    def trigger_repository_agent(
        self,
        repository_id: str,
        *,
        trigger: str,
        requested_by: str = "",
        root_path: str = "",
        manual_paths: list[str] | None = None,
        max_retries: int = 2,
        run_immediately: bool = False,
    ) -> dict | None:
        if not self.repository_service.get_repository(repository_id):
            return None
        return self.agent.trigger(
            repository_id,
            trigger=trigger,
            requested_by=requested_by,
            root_path=root_path,
            manual_paths=manual_paths,
            max_retries=max_retries,
            run_immediately=run_immediately,
        )

    def run_repository_agent_job(self, repository_id: str, job_id: str) -> dict | None:
        if not self.repository_service.get_repository(repository_id):
            return None
        job = self.agent.queue.get(job_id)
        if not job or (job.get("payload") or {}).get("repositoryId") != repository_id:
            return None
        return self.agent.run_job(job_id)

    def get_repository_agent_status(self, repository_id: str) -> dict | None:
        if not self.repository_service.get_repository(repository_id):
            return None
        return self.agent.status(repository_id)

    def list_repository_agent_jobs(self, repository_id: str, limit: int = 50) -> dict | None:
        if not self.repository_service.get_repository(repository_id):
            return None
        return self.agent.list_jobs(repository_id, limit=limit)

    def get_repository_monitoring(self, repository_id: str) -> dict | None:
        return self.monitoring_service.dashboard(repository_id)

    def get_repository_monitoring_dashboard(self) -> dict:
        return self.monitoring_service.dashboard_summary()

    def get_repository_health(self, repository_id: str) -> dict | None:
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            return None
        monitoring = self.monitoring_service.dashboard(repository_id) or {}
        snapshot = self.snapshot_service.get_latest_snapshot(repository_id)
        graph = self.graph_service.get_graph(repository_id)
        symbols = self.parser_service.list_symbols(repository_id, snapshot_id=snapshot.snapshot_id if snapshot else "")
        snapshot_metadata = dict(snapshot.metadata or {}) if snapshot else {}
        live_documentation = self.get_markdown_registry(repository_id) or {}
        documentation = {
            **dict(snapshot_metadata.get("documentationRegistry") or {}),
            **live_documentation,
        }
        graph_counts: dict[str, int] = {}
        graph_items: dict[str, list[dict]] = {}
        if graph:
            for node in graph.nodes:
                node_type = node.node_type.value
                graph_counts[node_type] = graph_counts.get(node_type, 0) + 1
                if node_type in {"Module", "Service", "Controller", "Repository", "API", "Test"}:
                    graph_items.setdefault(node_type, []).append(node.to_dict())
        symbol_counts: dict[str, int] = {}
        for symbol in symbols:
            kind = symbol.kind.value
            symbol_counts[kind] = symbol_counts.get(kind, 0) + 1
        jobs = self.agent.list_jobs(repository_id, limit=20)
        snapshots = list(reversed(self.snapshot_service.list_snapshots(repository_id)))[:8]
        latest_scan = monitoring.get("lastScan") if isinstance(monitoring.get("lastScan"), dict) else {}
        availability = "Available"
        if latest_scan.get("status") == "Failed":
            availability = "Offline" if snapshot else "Unavailable"
        elif not snapshot:
            availability = "Pending"
        return {
            **monitoring,
            "availability": availability,
            "branch": snapshot.branch if snapshot else repository.default_branch,
            "snapshotId": snapshot.snapshot_id if snapshot else "",
            "snapshotVersion": snapshot.version if snapshot else 0,
            "snapshotCreatedAt": snapshot.created_at if snapshot else "",
            "syncStatus": latest_scan.get("status") or repository.status.value,
            "engineeringGraphStatus": "Ready" if graph and graph.nodes else "Pending",
            "engineeringGraph": {
                "nodeCount": len(graph.nodes) if graph else 0,
                "relationshipCount": len(graph.relationships) if graph else 0,
                "counts": graph_counts,
            },
            "modules": [item["name"] for item in graph_items.get("Module", [])[:100]],
            "sourceRoots": list(snapshot_metadata.get("sourceRoots") or (snapshot.modules if snapshot else []))[:100],
            "folders": list(snapshot_metadata.get("folders") or [])[:500],
            "files": sorted(
                str(item.get("path") or "")
                for item in list(snapshot_metadata.get("files") or [])
                if isinstance(item, dict) and str(item.get("path") or "")
            )[:1000],
            "rootFiles": list(snapshot_metadata.get("rootFiles") or [])[:200],
            "documentation": documentation,
            "services": graph_items.get("Service", [])[:100],
            "controllers": graph_items.get("Controller", [])[:100],
            "repositories": graph_items.get("Repository", [])[:100],
            "apis": graph_items.get("API", [])[:100],
            "tests": graph_items.get("Test", [])[:100],
            "entities": [
                symbol.to_dict()
                for symbol in symbols
                if symbol.kind.value in {"Class", "Interface", "Enum"}
                and any(token in symbol.name.lower() for token in ("entity", "model", "record", "schema"))
            ][:100],
            "topModifiedFiles": _top_modified_files(snapshot_metadata, limit=10),
            "recentSnapshots": [item.to_dict() for item in snapshots],
            "syncHistory": [_repository_sync_summary(item) for item in jobs.get("jobs", [])[:10]],
            "symbolsIndexed": len(symbols),
            "symbolCounts": symbol_counts,
            "backgroundJobs": jobs.get("jobs", [])[:20],
            "backgroundJobSummary": {
                "total": jobs.get("count", 0),
                "pending": sum(1 for item in jobs.get("jobs", []) if item.get("status") in {"Queued", "Pending", "Running"}),
                "failed": sum(1 for item in jobs.get("jobs", []) if item.get("status") == "Failed"),
            },
            "warnings": _repository_health_warnings(repository, latest_scan, snapshot),
        }

    def cancel_scan(self, repository_id: str) -> dict | None:
        scan = self.scanner.cancel_scan(repository_id)
        return scan.to_dict() if scan else None

    def _build_repository_response(self, repository: Repository) -> dict:
        snapshot = self.snapshot_service.get_latest_snapshot(repository.repository_id)
        documentation = dict((snapshot.metadata or {}).get("documentationRegistry") or {}) if snapshot else {}
        graph = self.graph_service.get_graph_status(repository.repository_id)
        scan = self.scanner.get_scan(repository.repository_id)
        return {
            **repository.to_dict(),
            "latestSnapshotId": snapshot.snapshot_id if snapshot else "",
            "latestScanId": scan.scan_id if scan else "",
            "latestScanStatus": scan.status if scan else RepositoryStatus.PENDING_SCAN.value,
            "graphStatus": graph.get("status") or "NotConnected",
            "documentationStatus": documentation.get("status") or "NotIndexed",
            "markdownDocumentsIndexed": int(documentation.get("documentsIndexed") or 0),
        }

    def _validate_repository(self, repository: Repository) -> None:
        if not repository.name:
            raise ValueError("Repository name is required.")
        if not repository.url:
            raise ValueError("Repository URL is required.")
        if not self._is_valid_repository_url(repository.url, repository.repository_type.value):
            raise ValueError("Repository URL is not valid for the selected repository type.")

    def _is_valid_repository_url(self, value: str, repository_type: str) -> bool:
        parsed = urlparse(value)
        # Azure DevOps clone URLs may include the organization as user-info,
        # for example https://org@dev.azure.com/org/project/_git/repository.
        # Validate the hostname rather than the raw netloc so valid clone URLs
        # are not rejected because of their user-info component or port.
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        if repository_type == "AzureDevOps":
            return host == "dev.azure.com" or host.endswith(".visualstudio.com")
        if repository_type == "GitHub":
            return host == "github.com" or host.endswith(".github.com")
        return False


def _repository_health_warnings(repository: Repository, latest_scan: dict, snapshot: object | None) -> list[str]:
    warnings: list[str] = []
    if repository.status == RepositoryStatus.DISABLED:
        warnings.append("Repository synchronization is disabled.")
    if latest_scan.get("status") == "Failed":
        warnings.append("The latest repository synchronization failed.")
        if snapshot:
            warnings.append("The previous completed snapshot remains available.")
    if not snapshot:
        warnings.append("No completed repository snapshot is available.")
    return warnings


def _top_modified_files(metadata: dict, *, limit: int) -> list[dict]:
    diff = metadata.get("diff") if isinstance(metadata.get("diff"), dict) else {}
    output: list[dict] = []
    for change_type, key in (("Modified", "changed"), ("Added", "added"), ("Renamed", "renamed"), ("Deleted", "deleted")):
        for raw_path in list(diff.get(key) or []):
            if isinstance(raw_path, (list, tuple)):
                path = " -> ".join(str(item) for item in raw_path if str(item))
            else:
                path = str(raw_path or "")
            if path:
                output.append({"path": path, "changeType": change_type})
            if len(output) >= limit:
                return output
    return output


def _repository_sync_summary(job: dict) -> dict:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    return {
        "jobId": str(job.get("jobId") or ""),
        "status": str(job.get("status") or "Pending"),
        "trigger": str(payload.get("trigger") or job.get("source") or "Manual"),
        "mode": str(payload.get("mode") or ""),
        "requestedAt": str(job.get("createdAt") or job.get("requestedAt") or ""),
        "completedAt": str(job.get("completedAt") or job.get("updatedAt") or ""),
        "durationMs": int(job.get("durationMs") or 0),
        "error": str(job.get("error") or ""),
    }
