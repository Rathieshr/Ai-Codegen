"""Dependency registration for Repository Intelligence foundation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.engineering_memory.engine import EngineeringMemoryEngine
from backend.ado.client import AdoClient

from .application import RepositoryIntelligenceApplicationService
from .infrastructure import (
    FileBackedEngineeringGraphService,
    FileBackedRepositoryFileRankingService,
    FileBackedRepositoryParserService,
    FileBackedRepositoryService,
    FileBackedSnapshotService,
    FileSystemRepositoryScanner,
    RepositoryContextCapsuleBuilder,
    RepositoryIntelligenceAgent,
    RepositoryIntelligenceJobHandler,
    RepositoryMonitoringService,
)
from backend.platform.events import EventBus


@dataclass
class RepositoryIntelligenceModule:
    repository_service: FileBackedRepositoryService
    scanner: FileSystemRepositoryScanner
    snapshot_service: FileBackedSnapshotService
    graph_service: FileBackedEngineeringGraphService
    parser_service: FileBackedRepositoryParserService
    file_ranking_service: FileBackedRepositoryFileRankingService
    context_capsule_builder: RepositoryContextCapsuleBuilder
    agent: RepositoryIntelligenceAgent
    monitoring_service: RepositoryMonitoringService
    memory_engine: EngineeringMemoryEngine
    application: RepositoryIntelligenceApplicationService


def register_repository_intelligence(storage_root: Path) -> RepositoryIntelligenceModule:
    storage_root.mkdir(parents=True, exist_ok=True)
    ado_client = AdoClient()
    repository_service = FileBackedRepositoryService(storage_root / "repositories.json")
    snapshot_service = FileBackedSnapshotService(storage_root / "repository_snapshots.json")
    scanner = FileSystemRepositoryScanner(
        storage_root / "repository_scans.json",
        storage_root / "repository_snapshots.json",
        remote_item_provider=lambda repository: ado_client.list_repository_items(
            str(repository.metadata.get("adoProject") or ""),
            str(repository.metadata.get("azureDevOpsRepositoryId") or ""),
            str(repository.metadata.get("branch") or repository.default_branch or "main"),
        ),
    )
    graph_service = FileBackedEngineeringGraphService(storage_root / "engineering_graphs.json")
    parser_service = FileBackedRepositoryParserService(
        storage_root / "repository_symbols.json",
        remote_content_provider=lambda repository, path: ado_client.get_file_content(
            str(repository.metadata.get("adoProject") or ""),
            str(repository.metadata.get("azureDevOpsRepositoryId") or ""),
            path,
            str(repository.metadata.get("branch") or repository.default_branch or "main"),
        ),
    )
    memory_engine = EngineeringMemoryEngine(storage_root / "engineering_memory.json")
    file_ranking_service = FileBackedRepositoryFileRankingService(
        graph_service=graph_service,
        snapshot_service=snapshot_service,
        memory_engine=memory_engine,
    )
    context_capsule_builder = RepositoryContextCapsuleBuilder()
    event_bus = EventBus(storage_root / "repository_agent_events.json")
    agent_handler = RepositoryIntelligenceJobHandler(
        repository_service=repository_service,
        scanner=scanner,
        snapshot_service=snapshot_service,
        parser_service=parser_service,
        graph_service=graph_service,
        file_ranking_service=file_ranking_service,
        event_bus=event_bus,
    )
    agent = RepositoryIntelligenceAgent(storage_root, agent_handler)
    monitoring_service = RepositoryMonitoringService(
        repository_service=repository_service,
        scanner=scanner,
        snapshot_service=snapshot_service,
        graph_service=graph_service,
        agent=agent,
    )
    application = RepositoryIntelligenceApplicationService(
        repository_service=repository_service,
        scanner=scanner,
        snapshot_service=snapshot_service,
        graph_service=graph_service,
        parser_service=parser_service,
        file_ranking_service=file_ranking_service,
        context_capsule_builder=context_capsule_builder,
        agent=agent,
        monitoring_service=monitoring_service,
    )
    return RepositoryIntelligenceModule(
        repository_service=repository_service,
        scanner=scanner,
        snapshot_service=snapshot_service,
        graph_service=graph_service,
        parser_service=parser_service,
        file_ranking_service=file_ranking_service,
        context_capsule_builder=context_capsule_builder,
        agent=agent,
        monitoring_service=monitoring_service,
        memory_engine=memory_engine,
        application=application,
    )
