"""Repository Intelligence domain contracts."""

from __future__ import annotations

from typing import Protocol

from .engineering_graph import EngineeringGraph
from .entities import (
    RepositoryContextCapsule,
    Repository,
    RepositoryFileRanking,
    RepositoryParsedSymbol,
    RepositoryScan,
    RepositorySnapshot,
)


class IRepositoryService(Protocol):
    def create_repository(self, repository: Repository) -> Repository:
        ...

    def update_repository(self, repository_id: str, repository: Repository) -> Repository | None:
        ...

    def list_repositories(self) -> list[Repository]:
        ...

    def get_repository(self, repository_id: str) -> Repository | None:
        ...

    def delete_repository(self, repository_id: str) -> bool:
        ...

    def find_by_url(self, repository_url: str) -> Repository | None:
        ...

    def get_repository_status(self, repository_id: str) -> dict[str, object] | None:
        ...


class IRepositoryScanner(Protocol):
    def request_scan(
        self,
        repository_id: str,
        *,
        mode: str = "Full",
        requested_by: str = "",
        root_path: str = "",
        manual_paths: list[str] | None = None,
    ) -> RepositoryScan:
        ...

    def get_scan(self, repository_id: str) -> RepositoryScan | None:
        ...

    def run_scan(self, repository: Repository, scan: RepositoryScan) -> tuple[RepositoryScan, RepositorySnapshot]:
        ...

    def cancel_scan(self, repository_id: str) -> RepositoryScan | None:
        ...


class ISnapshotService(Protocol):
    def get_latest_snapshot(self, repository_id: str) -> RepositorySnapshot | None:
        ...

    def get_snapshot(self, repository_id: str, snapshot_id: str) -> RepositorySnapshot | None:
        ...

    def list_snapshots(self, repository_id: str) -> list[RepositorySnapshot]:
        ...

    def save_snapshot(self, snapshot: RepositorySnapshot) -> RepositorySnapshot:
        ...


class IEngineeringGraphService(Protocol):
    def get_graph_status(self, repository_id: str) -> dict[str, object]:
        ...

    def get_graph(self, repository_id: str) -> EngineeringGraph | None:
        ...

    def save_graph(self, graph: EngineeringGraph) -> EngineeringGraph:
        ...

    def query_nodes(
        self,
        repository_id: str,
        *,
        node_type: str = "",
        search: str = "",
    ) -> list[dict[str, object]]:
        ...

    def query_relationships(
        self,
        repository_id: str,
        *,
        relationship_type: str = "",
        from_node_id: str = "",
        to_node_id: str = "",
        search: str = "",
    ) -> list[dict[str, object]]:
        ...


class IRepositoryParserService(Protocol):
    def parse_snapshot(self, repository: Repository, snapshot: RepositorySnapshot) -> list[RepositoryParsedSymbol]:
        ...

    def save_symbols(
        self,
        repository_id: str,
        snapshot_id: str,
        symbols: list[RepositoryParsedSymbol],
    ) -> list[RepositoryParsedSymbol]:
        ...


class IFileRankingService(Protocol):
    def rank_files(
        self,
        repository: Repository,
        *,
        artifact_type: str,
        title: str,
        description: str = "",
        acceptance_criteria: list[str] | None = None,
        tags: list[str] | None = None,
        selected_modules: list[str] | None = None,
        selected_flows: list[str] | None = None,
        limit: int = 10,
    ) -> list[RepositoryFileRanking]:
        ...

    def list_symbols(
        self,
        repository_id: str,
        *,
        snapshot_id: str = "",
        language: str = "",
        kind: str = "",
        path: str = "",
        search: str = "",
    ) -> list[RepositoryParsedSymbol]:
        ...


class IContextCapsuleBuilder(Protocol):
    def build_capsule(
        self,
        *,
        story: dict[str, object],
        repository_snapshot: RepositorySnapshot | dict[str, object],
        engineering_graph: EngineeringGraph | dict[str, object] | None,
        repository_ranking: list[RepositoryFileRanking | dict[str, object] | str],
        selected_modules: list[str] | None = None,
        selected_flows: list[str] | None = None,
    ) -> RepositoryContextCapsule:
        ...
