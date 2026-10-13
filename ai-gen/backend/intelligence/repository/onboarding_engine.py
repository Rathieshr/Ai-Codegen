from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from backend.intelligence.graph import GraphBuilder, GraphDiagnostics

from .detectors import RepositoryDetectors
from .drift import calculate_repository_drift
from .repository_snapshot import RepositorySnapshot
from .scanner import RepositoryScanner
from .snapshot_store import RepositorySnapshotStore


class RepositoryOnboardingEngine:
    def __init__(
        self,
        *,
        scanner: RepositoryScanner | None = None,
        detectors: RepositoryDetectors | None = None,
        store: RepositorySnapshotStore | None = None,
    ) -> None:
        self.scanner = scanner or RepositoryScanner()
        self.detectors = detectors or RepositoryDetectors()
        self.store = store or RepositorySnapshotStore()

    def scanRepository(self, repository: dict[str, Any] | str) -> dict[str, Any]:
        return self.scanner.scan(repository)

    def buildRepositorySnapshot(self, repository: dict[str, Any] | str, *, persist: bool = True) -> dict[str, Any]:
        started = time.perf_counter()
        scan = self.scanRepository(repository)
        files = scan["files"]
        repository_id = scan["repositoryId"]
        previous = self.store.latest(repository_id)
        scan_version = self.store.next_version(repository_id)

        technologies = self.detectors.detect_technologies(files)
        architecture = self.detectors.detect_architecture(files)
        applications = self.detectors.discover_applications(files, scan)
        modules = self.detectors.discover_modules(files)
        flows = self.detectors.discover_flows(files)
        dependencies = self.detectors.discover_dependencies(files)
        relationships = self.detectors.discover_code_relationships(files)
        patterns = self.detectors.discover_patterns(files)
        standards = self.detectors.discover_standards(files)

        graph = self.updateEngineeringGraph(
            {
                "repositoryId": repository_id,
                "files": [file.to_dict() for file in files],
                "source_files": scan.get("documentation", []),
            },
            {
                "applications": [item.to_dict() for item in applications],
                "modules": [item.to_dict() for item in modules],
                "flows": [item.to_dict() for item in flows],
                "dependencies": [item.to_dict() for item in dependencies],
                "standards": [item.to_dict() for item in standards],
            },
        )
        graph_summary = GraphDiagnostics(graph).summary()
        confidence = _average_confidence([technologies, architecture, applications, modules, flows, patterns, standards])
        snapshot = RepositorySnapshot(
            repository_id=repository_id,
            scan_version=scan_version,
            scanned_at=datetime.now(timezone.utc).isoformat(),
            applications=applications,
            modules=modules,
            flows=flows,
            technologies=technologies,
            architecture=architecture,
            dependencies=dependencies,
            patterns=patterns,
            standards=standards,
            services=relationships["services"],
            apis=relationships["apis"],
            database_models=relationships["database_models"],
            files=files,
            source_files=scan.get("documentation", []),
            graph_statistics={
                "nodes": graph_summary["node_count"],
                "edges": graph_summary["edge_count"],
                "healthScore": graph_summary["health_score"],
            },
            confidence=confidence,
            diagnostics={
                "scanDurationMs": int((time.perf_counter() - started) * 1000),
                "projectsScanned": len(scan.get("projects", [])),
                "filesScanned": len(files),
                "modulesDiscovered": len(modules),
                "flowsDiscovered": len(flows),
                "architectureConfidence": max([item.confidence for item in architecture], default=0.0),
                "technologyConfidence": max([item.confidence for item in technologies], default=0.0),
                "graphNodes": graph_summary["node_count"],
                "graphEdges": graph_summary["edge_count"],
                "errors": [],
                "warnings": scan.get("warnings", []),
            },
        )
        drift = self.calculateRepositoryDrift(previous, snapshot)
        knowledge_registry = self.updateKnowledgeRegistry({}, snapshot)
        saved = self.store.save(snapshot) if persist else {}
        return {
            "repositorySnapshot": snapshot.to_dict(),
            "knowledgeRegistry": knowledge_registry,
            "engineeringGraph": graph.to_dict(),
            "repositoryDrift": drift,
            "snapshotHistory": {
                "repositoryId": repository_id,
                "latestVersion": scan_version,
                "previousVersion": previous.scan_version if previous else None,
                "saved": saved,
            },
            "diagnostics": {
                **snapshot.diagnostics,
                "knowledgeUpdates": _count_registry_updates(knowledge_registry),
                "repositoryDrift": drift["status"],
            },
        }

    def discoverModules(self, files: list[Any]) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.detectors.discover_modules(files)]

    def discoverFlows(self, files: list[Any]) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.detectors.discover_flows(files)]

    def discoverArchitecture(self, files: list[Any]) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.detectors.detect_architecture(files)]

    def discoverPatterns(self, files: list[Any]) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.detectors.discover_patterns(files)]

    def updateKnowledgeRegistry(self, existing: dict[str, Any], snapshot: RepositorySnapshot) -> dict[str, Any]:
        registry = {key: list(value) if isinstance(value, list) else value for key, value in (existing or {}).items()}
        for key, items in {
            "applications": snapshot.applications,
            "modules": snapshot.modules,
            "flows": snapshot.flows,
            "patterns": snapshot.patterns,
            "standards": snapshot.standards,
            "technologies": snapshot.technologies,
            "dependencies": snapshot.dependencies,
            "source_files": snapshot.source_files,
        }.items():
            current = registry.get(key, []) if isinstance(registry.get(key, []), list) else []
            additions = [item if isinstance(item, str) else item.name for item in items]
            if key == "source_files":
                additions = list(items)
            registry[key] = _dedupe([*current, *additions])
        registry["repository_mappings"] = _dedupe([*registry.get("repository_mappings", []), snapshot.repository_id])
        registry["snapshot_version"] = snapshot.scan_version
        return registry

    def updateEngineeringGraph(self, repository_snapshot: dict[str, Any], knowledge_registry: dict[str, Any]):
        return GraphBuilder().build_engineering_graph(
            project_profile={"project_id": repository_snapshot.get("repositoryId"), "project_name": repository_snapshot.get("repositoryId")},
            repository_snapshot=repository_snapshot,
            knowledge_registry=knowledge_registry,
        )

    def calculateRepositoryDrift(self, previous: RepositorySnapshot | None, current: RepositorySnapshot) -> dict[str, Any]:
        return calculate_repository_drift(previous, current)


def _average_confidence(groups: list[list[Any]]) -> float:
    values = [float(item.confidence) for group in groups for item in group]
    return round(sum(values) / len(values), 3) if values else 0.0


def _dedupe(values: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        key = str(value).strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _count_registry_updates(registry: dict[str, Any]) -> int:
    total = 0
    for value in registry.values():
        if isinstance(value, list):
            total += len(value)
    return total
