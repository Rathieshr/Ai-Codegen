"""Dependency registration for Repository Intelligence foundation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.engineering_memory.engine import EngineeringMemoryEngine
from backend.engineering_intelligence.services import MarkdownService
from backend.ado.client import AdoClient

from .application import RepositoryDetectionService, RepositoryIntelligenceApplicationService
from backend.platform.shared import JsonMapStore
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
    markdown_service: MarkdownService
    memory_engine: EngineeringMemoryEngine
    detection_service: RepositoryDetectionService
    application: RepositoryIntelligenceApplicationService


def register_repository_intelligence(storage_root: Path) -> RepositoryIntelligenceModule:
    storage_root.mkdir(parents=True, exist_ok=True)
    ado_client = AdoClient()
    remote_content_provider = lambda repository, path: ado_client.get_file_content(
        str(repository.metadata.get("adoProject") or ""),
        str(repository.metadata.get("azureDevOpsRepositoryId") or ""),
        path,
        str(repository.metadata.get("branch") or repository.default_branch or "main"),
    )
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
        remote_content_provider=remote_content_provider,
    )
    memory_engine = EngineeringMemoryEngine(storage_root / "engineering_memory.json")
    detection_service = RepositoryDetectionService(
        repository_service=repository_service,
        snapshot_service=snapshot_service,
        memory_engine=memory_engine,
        suggestion_store=JsonMapStore(storage_root / "repository_suggestions.json"),
        override_store=JsonMapStore(storage_root / "repository_detection_overrides.json"),
    )
    file_ranking_service = FileBackedRepositoryFileRankingService(
        graph_service=graph_service,
        snapshot_service=snapshot_service,
        memory_engine=memory_engine,
    )
    context_capsule_builder = RepositoryContextCapsuleBuilder()
    markdown_service = MarkdownService(
        storage_path=storage_root / "repository_markdown_registry.json",
    )
    event_bus = EventBus(storage_root / "repository_agent_events.json")
    agent_handler = RepositoryIntelligenceJobHandler(
        repository_service=repository_service,
        scanner=scanner,
        snapshot_service=snapshot_service,
        parser_service=parser_service,
        graph_service=graph_service,
        file_ranking_service=file_ranking_service,
        event_bus=event_bus,
        markdown_service=markdown_service,
        repository_content_provider=remote_content_provider,
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
        repository_content_provider=remote_content_provider,
        markdown_service=markdown_service,
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
        markdown_service=markdown_service,
        memory_engine=memory_engine,
        detection_service=detection_service,
        application=application,
    )
