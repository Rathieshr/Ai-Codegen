"""Infrastructure implementations for Repository Intelligence."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from backend.platform.shared import JsonListStore, generated_id, now_iso

from ..domain import (
    EngineeringGraph,
    EngineeringNode,
    EngineeringNodeType,
    EngineeringRelationship,
    IEngineeringGraphService,
    IRepositoryScanner,
    IRepositoryService,
    ISnapshotService,
    Repository,
    RepositoryFile,
    RepositoryLanguage,
    RepositoryParsedSymbol,
    RepositoryScan,
    RepositorySnapshot,
    RepositoryStatus,
    RepositorySymbolKind,
    RelationshipType,
)


class FileBackedRepositoryService(IRepositoryService):
    def __init__(self, storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)

    def create_repository(self, repository: Repository) -> Repository:
        items = [Repository.from_dict(item) for item in self._store.read()]
        created = Repository.from_dict(
            {
                **repository.to_dict(),
                "repositoryId": repository.repository_id,
                "createdAt": repository.created_at or now_iso(),
                "updatedAt": now_iso(),
                "status": repository.status.value or RepositoryStatus.PENDING_SCAN.value,
            }
        )
        items.append(created)
        self._store.write([item.to_dict() for item in items])
        return created

    def update_repository(self, repository_id: str, repository: Repository) -> Repository | None:
        items = [Repository.from_dict(item) for item in self._store.read()]
        for index, existing in enumerate(items):
            if existing.repository_id == repository_id:
                updated = Repository.from_dict(
                    {
                        **repository.to_dict(),
                        "repositoryId": repository_id,
                        "createdAt": existing.created_at,
                        "updatedAt": now_iso(),
                    }
                )
                items[index] = updated
                self._store.write([item.to_dict() for item in items])
                return updated
        return None

    def list_repositories(self) -> list[Repository]:
        return [Repository.from_dict(item) for item in self._store.read()]

    def get_repository(self, repository_id: str) -> Repository | None:
        for item in self._store.read():
            repository = Repository.from_dict(item)
            if repository.repository_id == repository_id:
                return repository
        return None

    def delete_repository(self, repository_id: str) -> bool:
        items = [Repository.from_dict(item) for item in self._store.read()]
        filtered = [item for item in items if item.repository_id != repository_id]
        if len(filtered) == len(items):
            return False
        self._store.write([item.to_dict() for item in filtered])
        return True

    def find_by_url(self, repository_url: str) -> Repository | None:
        normalized = repository_url.strip().rstrip("/").lower()
        for item in self._store.read():
            repository = Repository.from_dict(item)
            if repository.url.strip().rstrip("/").lower() == normalized:
                return repository
        return None

    def get_repository_status(self, repository_id: str) -> dict[str, object] | None:
        repository = self.get_repository(repository_id)
        if not repository:
            return None
        return {
            "repositoryId": repository_id,
            "status": repository.status.value,
            "scanStatus": RepositoryStatus.PENDING_SCAN.value,
            "snapshotStatus": "NotAvailable",
            "message": "Repository Intelligence foundation is registered. Scanning is not implemented yet.",
        }


class FileBackedSnapshotService(ISnapshotService):
    def __init__(self, storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)

    def get_latest_snapshot(self, repository_id: str) -> RepositorySnapshot | None:
        snapshots = self.list_snapshots(repository_id)
        return snapshots[-1] if snapshots else None

    def get_snapshot(self, repository_id: str, snapshot_id: str) -> RepositorySnapshot | None:
        for snapshot in self.list_snapshots(repository_id):
            if snapshot.snapshot_id == snapshot_id:
                return snapshot
        return None

    def list_snapshots(self, repository_id: str) -> list[RepositorySnapshot]:
        snapshots = [RepositorySnapshot.from_dict(item) for item in self._store.read()]
        filtered = [snapshot for snapshot in snapshots if snapshot.repository_id == repository_id]
        return sorted(filtered, key=lambda snapshot: (snapshot.version, snapshot.created_at))

    def save_snapshot(self, snapshot: RepositorySnapshot) -> RepositorySnapshot:
        snapshots = [RepositorySnapshot.from_dict(item) for item in self._store.read()]
        snapshots.append(snapshot)
        self._store.write([item.to_dict() for item in snapshots])
        return snapshot


class FileBackedEngineeringGraphService(IEngineeringGraphService):
    def __init__(self, storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)

    def get_graph_status(self, repository_id: str) -> dict[str, object]:
        graph = self.get_graph(repository_id)
        if not graph:
            return {
                "repositoryId": repository_id,
                "status": "NotConnected",
                "message": "Engineering graph foundation is registered but not initialized.",
                "nodeCount": 0,
                "relationshipCount": 0,
            }
        return {
            "repositoryId": repository_id,
            "status": "Available",
            "message": "Engineering graph foundation is available.",
            "nodeCount": len(graph.nodes),
            "relationshipCount": len(graph.relationships),
        }

    def get_graph(self, repository_id: str) -> EngineeringGraph | None:
        for item in self._store.read():
            graph = EngineeringGraph.from_dict(item)
            if graph.repository_id == repository_id:
                return graph
        return None

    def save_graph(self, graph: EngineeringGraph) -> EngineeringGraph:
        graphs = [EngineeringGraph.from_dict(item) for item in self._store.read()]
        graphs = [item for item in graphs if item.repository_id != graph.repository_id]
        graphs.append(graph)
        self._store.write([item.to_dict() for item in graphs])
        return graph

    def query_nodes(
        self,
        repository_id: str,
        *,
        node_type: str = "",
        search: str = "",
    ) -> list[dict[str, object]]:
        graph = self.get_graph(repository_id)
        if not graph:
            return []
        normalized_type = node_type.strip().lower()
        normalized_search = search.strip().lower()
        nodes = graph.nodes
        if normalized_type:
            nodes = [node for node in nodes if node.node_type.value.lower() == normalized_type]
        if normalized_search:
            nodes = [node for node in nodes if normalized_search in node.name.lower() or normalized_search in node.path.lower()]
        return [node.to_dict() for node in nodes]

    def query_relationships(
        self,
        repository_id: str,
        *,
        relationship_type: str = "",
        from_node_id: str = "",
        to_node_id: str = "",
        search: str = "",
    ) -> list[dict[str, object]]:
        graph = self.get_graph(repository_id)
        if not graph:
            return []
        relationship_type = relationship_type.strip().lower()
        from_node_id = from_node_id.strip()
        to_node_id = to_node_id.strip()
        search = search.strip().lower()
        relationships = graph.relationships
        if relationship_type:
            relationships = [
                item for item in relationships if item.relationship_type.value.lower() == relationship_type
            ]
        if from_node_id:
            relationships = [item for item in relationships if item.from_node_id == from_node_id]
        if to_node_id:
            relationships = [item for item in relationships if item.to_node_id == to_node_id]
        if search:
            relationships = [
                item
                for item in relationships
                if search in item.from_node_id.lower()
                or search in item.to_node_id.lower()
                or search in str(item.metadata).lower()
            ]
        return [item.to_dict() for item in relationships]

    def build_foundation_graph(
        self,
        repository: Repository,
        snapshot: RepositorySnapshot,
        symbols: list[RepositoryParsedSymbol],
    ) -> EngineeringGraph:
        repository_node = EngineeringNode(
            node_id=f"repository:{repository.repository_id}",
            repository_id=repository.repository_id,
            node_type=EngineeringNodeType.REPOSITORY,
            name=repository.name,
            path=repository.url,
            metadata={
                "defaultBranch": repository.default_branch,
                "snapshotId": snapshot.snapshot_id,
                "snapshotVersion": snapshot.version,
            },
        )
        module_nodes = [
            EngineeringNode(
                node_id=f"module:{repository.repository_id}:{module.lower().replace(' ', '-')}",
                repository_id=repository.repository_id,
                node_type=EngineeringNodeType.MODULE,
                name=module,
                path=module,
                metadata={
                    "snapshotId": snapshot.snapshot_id,
                    "snapshotVersion": snapshot.version,
                },
            )
            for module in snapshot.modules
        ]
        files = list((snapshot.metadata or {}).get("files") or [])
        file_nodes = [
            EngineeringNode(
                node_id=self._file_node_id(repository.repository_id, str(file_record.get("path") or "")),
                repository_id=repository.repository_id,
                node_type=EngineeringNodeType.FILE,
                name=Path(str(file_record.get("path") or "")).name or str(file_record.get("path") or ""),
                path=str(file_record.get("path") or ""),
                metadata={
                    "snapshotId": snapshot.snapshot_id,
                    "snapshotVersion": snapshot.version,
                    "language": str(file_record.get("language") or RepositoryLanguage.UNKNOWN.value),
                    "extension": str(file_record.get("extension") or ""),
                    "size": int(file_record.get("size") or 0),
                },
            )
            for file_record in files
            if str(file_record.get("path") or "")
        ]
        symbol_nodes = self._build_symbol_nodes(repository.repository_id, snapshot, symbols)
        ui_nodes = self._build_ui_nodes(repository.repository_id, snapshot, files)
        nodes = self._dedupe_nodes([repository_node, *module_nodes, *file_nodes, *symbol_nodes, *ui_nodes])
        relationships = self._build_relationships(
            repository=repository,
            snapshot=snapshot,
            files=files,
            symbols=symbols,
            nodes=nodes,
        )
        return EngineeringGraph(
            graph_id=f"graph:{repository.repository_id}",
            repository_id=repository.repository_id,
            nodes=nodes,
            relationships=relationships,
            metadata={
                "snapshotId": snapshot.snapshot_id,
                "snapshotVersion": snapshot.version,
                "branch": snapshot.branch,
                "commitId": snapshot.commit_id,
                "status": snapshot.status,
                "scanMode": snapshot.scan_mode,
            },
        )

    def _build_symbol_nodes(
        self,
        repository_id: str,
        snapshot: RepositorySnapshot,
        symbols: list[RepositoryParsedSymbol],
    ) -> list[EngineeringNode]:
        nodes: list[EngineeringNode] = []
        for symbol in symbols:
            node_type = self._symbol_node_type(symbol)
            if not node_type:
                continue
            nodes.append(
                EngineeringNode(
                    node_id=self._symbol_node_id(repository_id, symbol),
                    repository_id=repository_id,
                    node_type=node_type,
                    name=symbol.name,
                    path=symbol.path,
                    metadata={
                        "snapshotId": snapshot.snapshot_id,
                        "snapshotVersion": snapshot.version,
                        "symbolKind": symbol.kind.value,
                        "namespace": symbol.namespace,
                        "container": symbol.container,
                        "language": symbol.language.value,
                    },
                )
            )
        return nodes

    def _build_ui_nodes(
        self,
        repository_id: str,
        snapshot: RepositorySnapshot,
        files: list[dict[str, object]],
    ) -> list[EngineeringNode]:
        nodes: list[EngineeringNode] = []
        for file_record in files:
            path = str(file_record.get("path") or "")
            if not path or not self._is_ui_file(path, str(file_record.get("language") or "")):
                continue
            nodes.append(
                EngineeringNode(
                    node_id=self._ui_node_id(repository_id, path),
                    repository_id=repository_id,
                    node_type=EngineeringNodeType.UI,
                    name=Path(path).stem,
                    path=path,
                    metadata={
                        "snapshotId": snapshot.snapshot_id,
                        "snapshotVersion": snapshot.version,
                        "language": str(file_record.get("language") or RepositoryLanguage.UNKNOWN.value),
                    },
                )
            )
        return nodes

    def _build_relationships(
        self,
        *,
        repository: Repository,
        snapshot: RepositorySnapshot,
        files: list[dict[str, object]],
        symbols: list[RepositoryParsedSymbol],
        nodes: list[EngineeringNode],
    ) -> list[EngineeringRelationship]:
        relationships: list[EngineeringRelationship] = []
        repository_id = repository.repository_id
        repository_root = Path(str(repository.metadata.get("localPath") or "")).expanduser()
        node_by_id = {node.node_id: node for node in nodes}
        module_by_name = {
            node.name: node for node in nodes if node.node_type == EngineeringNodeType.MODULE
        }
        file_by_path = {
            str(file_record.get("path") or ""): file_record
            for file_record in files
            if str(file_record.get("path") or "")
        }
        content_cache = self._content_cache(repository_root, file_by_path)
        symbols_by_kind: dict[RepositorySymbolKind, list[RepositoryParsedSymbol]] = {}
        path_symbols: dict[str, list[RepositoryParsedSymbol]] = {}
        for symbol in symbols:
            symbols_by_kind.setdefault(symbol.kind, []).append(symbol)
            path_symbols.setdefault(symbol.path, []).append(symbol)

        for file_record in files:
            path = str(file_record.get("path") or "")
            if not path:
                continue
            module_name = path.split("/", 1)[0] if "/" in path else path
            module_node = module_by_name.get(module_name)
            file_node = node_by_id.get(self._file_node_id(repository_id, path))
            if module_node and file_node:
                relationships.append(
                    self._relationship(
                        repository_id,
                        module_node.node_id,
                        file_node.node_id,
                        RelationshipType.CONTAINS,
                        reason="module_file_membership",
                        snapshot=snapshot,
                    )
                )

        for controller in symbols_by_kind.get(RepositorySymbolKind.CONTROLLER, []):
            targets = self._match_targets(
                controller,
                symbols_by_kind.get(RepositorySymbolKind.SERVICE, []),
                content_cache.get(controller.path, ""),
            )
            relationships.extend(
                self._symbol_relationships(
                    repository_id,
                    controller,
                    targets,
                    RelationshipType.DEPENDS_ON,
                    reason="controller_service_reference",
                    snapshot=snapshot,
                )
            )

        for service in symbols_by_kind.get(RepositorySymbolKind.SERVICE, []):
            targets = self._match_targets(
                service,
                symbols_by_kind.get(RepositorySymbolKind.REPOSITORY, []),
                content_cache.get(service.path, ""),
            )
            relationships.extend(
                self._symbol_relationships(
                    repository_id,
                    service,
                    targets,
                    RelationshipType.DEPENDS_ON,
                    reason="service_repository_reference",
                    snapshot=snapshot,
                )
            )

        api_candidates = self._api_targets(symbols_by_kind)
        dto_candidates = self._dto_candidates(symbols, content_cache)
        for dto in dto_candidates:
            targets = self._match_targets(dto, api_candidates, content_cache.get(dto.path, ""))
            if not targets:
                targets = [
                    api_target
                    for api_target in api_candidates
                    if self._content_mentions(content_cache.get(api_target.path, ""), dto.name)
                ]
            relationships.extend(
                self._symbol_relationships(
                    repository_id,
                    dto,
                    targets,
                    RelationshipType.REFERENCES,
                    reason="dto_api_contract_reference",
                    snapshot=snapshot,
                )
            )

        for test_symbol in symbols_by_kind.get(RepositorySymbolKind.TEST, []):
            targets = self._match_targets(
                test_symbol,
                symbols_by_kind.get(RepositorySymbolKind.SERVICE, []),
                content_cache.get(test_symbol.path, ""),
                allow_name_overlap=True,
            )
            relationships.extend(
                self._symbol_relationships(
                    repository_id,
                    test_symbol,
                    targets,
                    RelationshipType.TESTS,
                    reason="test_service_coverage",
                    snapshot=snapshot,
                )
            )

        ui_nodes = [node for node in nodes if node.node_type == EngineeringNodeType.UI]
        api_node_targets = [
            node for node in nodes if node.node_type == EngineeringNodeType.API
        ]
        for ui_node in ui_nodes:
            content = content_cache.get(ui_node.path, "")
            matched_api_nodes = [
                api_node
                for api_node in api_node_targets
                if self._content_mentions(content, api_node.name)
                or self._content_mentions(content, str(api_node.metadata.get("route") or ""))
            ]
            for api_node in matched_api_nodes:
                relationships.append(
                    self._relationship(
                        repository_id,
                        ui_node.node_id,
                        api_node.node_id,
                        RelationshipType.DEPENDS_ON,
                        reason="ui_api_reference",
                        snapshot=snapshot,
                    )
                )

        return self._dedupe_relationships(relationships)

    def _content_cache(
        self,
        repository_root: Path,
        file_by_path: dict[str, dict[str, object]],
    ) -> dict[str, str]:
        if not repository_root.exists():
            return {}
        result: dict[str, str] = {}
        for path in file_by_path:
            full_path = (repository_root / path).resolve()
            if full_path.exists() and full_path.is_file():
                result[path] = full_path.read_text(encoding="utf-8", errors="ignore")
        return result

    def _api_targets(
        self,
        symbols_by_kind: dict[RepositorySymbolKind, list[RepositoryParsedSymbol]],
    ) -> list[RepositoryParsedSymbol]:
        routes = list(symbols_by_kind.get(RepositorySymbolKind.ROUTE, []))
        if routes:
            return routes
        return list(symbols_by_kind.get(RepositorySymbolKind.CONTROLLER, []))

    def _dto_candidates(
        self,
        symbols: list[RepositoryParsedSymbol],
        content_cache: dict[str, str],
    ) -> list[RepositoryParsedSymbol]:
        candidates: list[RepositoryParsedSymbol] = []
        for symbol in symbols:
            if symbol.kind not in {RepositorySymbolKind.CLASS, RepositorySymbolKind.INTERFACE}:
                continue
            lowered = symbol.name.lower()
            if lowered.endswith("dto") or "/dto" in symbol.path.lower() or "/contracts/" in symbol.path.lower():
                candidates.append(symbol)
                continue
            content = content_cache.get(symbol.path, "")
            if re.search(r"\b(request|response|contract|dto)\b", content, flags=re.IGNORECASE):
                candidates.append(symbol)
        return candidates

    def _match_targets(
        self,
        source_symbol: RepositoryParsedSymbol,
        target_symbols: list[RepositoryParsedSymbol],
        content: str,
        *,
        allow_name_overlap: bool = False,
    ) -> list[RepositoryParsedSymbol]:
        if not target_symbols or not content:
            return []
        matched: list[RepositoryParsedSymbol] = []
        normalized_content = content.lower()
        source_base = Path(source_symbol.path).stem.lower()
        for target in target_symbols:
            if source_symbol.path == target.path and source_symbol.name == target.name:
                continue
            target_name = target.name.strip()
            if not target_name:
                continue
            if self._content_mentions(normalized_content, target_name):
                matched.append(target)
                continue
            if allow_name_overlap and target_name.lower().replace("service", "") in source_base:
                matched.append(target)
        return self._dedupe_symbol_list(matched)

    def _symbol_relationships(
        self,
        repository_id: str,
        source_symbol: RepositoryParsedSymbol,
        targets: list[RepositoryParsedSymbol],
        relationship_type: RelationshipType,
        *,
        reason: str,
        snapshot: RepositorySnapshot,
    ) -> list[EngineeringRelationship]:
        source_node_id = self._symbol_node_id(repository_id, source_symbol)
        relationships: list[EngineeringRelationship] = []
        for target in targets:
            target_node_id = self._symbol_node_id(repository_id, target)
            relationships.append(
                self._relationship(
                    repository_id,
                    source_node_id,
                    target_node_id,
                    relationship_type,
                    reason=reason,
                    snapshot=snapshot,
                    metadata={
                        "sourcePath": source_symbol.path,
                        "targetPath": target.path,
                    },
                )
            )
        return relationships

    def _relationship(
        self,
        repository_id: str,
        from_node_id: str,
        to_node_id: str,
        relationship_type: RelationshipType,
        *,
        reason: str,
        snapshot: RepositorySnapshot,
        metadata: dict[str, object] | None = None,
    ) -> EngineeringRelationship:
        return EngineeringRelationship(
            relationship_id=generated_id("graph_relationship"),
            repository_id=repository_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            relationship_type=relationship_type,
            metadata={
                "reason": reason,
                "snapshotId": snapshot.snapshot_id,
                "snapshotVersion": snapshot.version,
                **(metadata or {}),
            },
        )

    def _symbol_node_type(self, symbol: RepositoryParsedSymbol) -> EngineeringNodeType | None:
        mapping = {
            RepositorySymbolKind.CONTROLLER: EngineeringNodeType.CONTROLLER,
            RepositorySymbolKind.SERVICE: EngineeringNodeType.SERVICE,
            RepositorySymbolKind.REPOSITORY: EngineeringNodeType.REPOSITORY,
            RepositorySymbolKind.TEST: EngineeringNodeType.TEST,
            RepositorySymbolKind.ROUTE: EngineeringNodeType.API,
        }
        node_type = mapping.get(symbol.kind)
        if node_type:
            return node_type
        if symbol.kind in {RepositorySymbolKind.CLASS, RepositorySymbolKind.INTERFACE}:
            lowered = symbol.name.lower()
            if lowered.endswith("dto") or "dto" in symbol.path.lower() or "contracts" in symbol.path.lower():
                return EngineeringNodeType.DTO
        return None

    def _is_ui_file(self, path: str, language: str) -> bool:
        normalized_path = path.lower()
        normalized_language = language.lower()
        if normalized_language in {"xaml", "xml"}:
            return True
        ui_markers = ("/ui/", "/views/", "/viewmodels/", "/screens/", "/pages/", "/components/")
        if any(marker in normalized_path for marker in ui_markers):
            return True
        return normalized_path.endswith((".tsx", ".jsx", ".xaml"))

    def _content_mentions(self, content: str, value: str) -> bool:
        if not value:
            return False
        return value.lower() in content.lower()

    def _file_node_id(self, repository_id: str, path: str) -> str:
        return f"file:{repository_id}:{path}"

    def _ui_node_id(self, repository_id: str, path: str) -> str:
        return f"ui:{repository_id}:{path}"

    def _symbol_node_id(self, repository_id: str, symbol: RepositoryParsedSymbol) -> str:
        kind = symbol.kind.value.lower()
        return f"{kind}:{repository_id}:{symbol.path}:{symbol.name}"

    def _dedupe_nodes(self, nodes: list[EngineeringNode]) -> list[EngineeringNode]:
        seen: dict[str, EngineeringNode] = {}
        for node in nodes:
            seen[node.node_id] = node
        return list(seen.values())

    def _dedupe_relationships(
        self,
        relationships: list[EngineeringRelationship],
    ) -> list[EngineeringRelationship]:
        seen: dict[tuple[str, str, str], EngineeringRelationship] = {}
        for relationship in relationships:
            key = (
                relationship.from_node_id,
                relationship.to_node_id,
                relationship.relationship_type.value,
            )
            if key not in seen:
                seen[key] = relationship
        return list(seen.values())

    def _dedupe_symbol_list(
        self,
        items: list[RepositoryParsedSymbol],
    ) -> list[RepositoryParsedSymbol]:
        seen: dict[tuple[str, str, str], RepositoryParsedSymbol] = {}
        for item in items:
            key = (item.path, item.kind.value, item.name)
            seen[key] = item
        return list(seen.values())


class FileSystemRepositoryScanner(IRepositoryScanner):
    def __init__(self, storage_path: Path, snapshot_storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)
        self._snapshot_store = JsonListStore(snapshot_storage_path)

    def request_scan(
        self,
        repository_id: str,
        *,
        mode: str = "Full",
        requested_by: str = "",
        root_path: str = "",
        manual_paths: list[str] | None = None,
    ) -> RepositoryScan:
        scan = RepositoryScan(
            scan_id=generated_id("repository_scan"),
            repository_id=repository_id,
            requested_by=requested_by,
            mode=mode or "Full",
            root_path=root_path,
            progress={
                "currentStep": "Queued",
                "completedSteps": [],
                "pendingSteps": ["Scanning", "Persist Results"],
                "percentComplete": 0,
                "updatedAt": now_iso(),
            },
            metadata={"manualPaths": list(manual_paths or [])},
        )
        items = [RepositoryScan.from_dict(item) for item in self._store.read()]
        items = [item for item in items if item.repository_id != repository_id]
        items.append(scan)
        self._store.write([item.to_dict() for item in items])
        return scan

    def get_scan(self, repository_id: str) -> RepositoryScan | None:
        for item in self._store.read():
            scan = RepositoryScan.from_dict(item)
            if scan.repository_id == repository_id:
                return scan
        return None

    def cancel_scan(self, repository_id: str) -> RepositoryScan | None:
        scan = self.get_scan(repository_id)
        if not scan:
            return None
        if scan.status == "Completed":
            return scan
        updated = RepositoryScan.from_dict(
            {
                **scan.to_dict(),
                "status": "Cancelled",
                "completedAt": now_iso(),
                "progress": {
                    **scan.progress,
                    "currentStep": "Cancelled",
                    "percentComplete": scan.progress.get("percentComplete", 0),
                    "updatedAt": now_iso(),
                },
                "message": "Repository scan was cancelled.",
            }
        )
        self._save_scan(updated)
        return updated

    def run_scan(self, repository: Repository, scan: RepositoryScan) -> tuple[RepositoryScan, RepositorySnapshot]:
        root_path = scan.root_path or str(repository.metadata.get("localPath") or "")
        root = Path(root_path).expanduser()
        git_context = self._detect_git_context(root)
        if scan.status == "Cancelled":
            return scan, self._empty_snapshot(repository.repository_id, scan.mode)
        if not root_path:
            failed = self._update_scan(
                scan,
                status="Failed",
                message="Repository local path is required in metadata.localPath or scan rootPath.",
                completed_at=now_iso(),
            )
            return failed, self._empty_snapshot(repository.repository_id, scan.mode)
        if not root.exists() or not root.is_dir():
            failed = self._update_scan(
                scan,
                status="Failed",
                message=f"Repository path '{root}' does not exist or is not a directory.",
                completed_at=now_iso(),
            )
            return failed, self._empty_snapshot(repository.repository_id, scan.mode)

        scanning = self._update_scan(
            scan,
            status="Scanning",
            started_at=now_iso(),
            message="Repository structure scan in progress.",
            progress={
                "currentStep": "Scanning",
                "completedSteps": ["Queued"],
                "pendingSteps": ["Persist Results"],
                "percentComplete": 10,
                "startedAt": now_iso(),
                "updatedAt": now_iso(),
            },
        )

        previous_snapshot = self._get_latest_snapshot(repository.repository_id)
        if scanning.mode == "Incremental":
            folders, files, diff = self._collect_incremental_structure(
                root,
                repository,
                previous_snapshot,
                git_context,
            )
        else:
            folders, files = self._collect_structure(root, scanning.mode, scanning.metadata.get("manualPaths") or [])
            diff = {}
        snapshot = self._build_snapshot(repository, scanning.mode, folders, files, diff, git_context)

        completed = self._update_scan(
            scanning,
            status="Completed",
            completed_at=now_iso(),
            message="Repository structure scan completed.",
            progress={
                "currentStep": "Completed",
                "completedSteps": ["Queued", "Scanning", "Persist Results"],
                "pendingSteps": [],
                "percentComplete": 100,
                "startedAt": scanning.started_at or now_iso(),
                "updatedAt": now_iso(),
                "foldersDiscovered": len(folders),
                "filesDiscovered": len(files),
            },
            metadata={
                **scanning.metadata,
                "foldersDiscovered": len(folders),
                "filesDiscovered": len(files),
                "changedFileCount": int(diff.get("changedFileCount") or 0),
            },
        )
        return completed, snapshot

    def _collect_incremental_structure(
        self,
        root: Path,
        repository: Repository,
        previous_snapshot: RepositorySnapshot | None,
        git_context: dict[str, str],
    ) -> tuple[list[str], list[dict[str, object]], dict[str, object]]:
        if not previous_snapshot:
            folders, files = self._collect_structure(root, "Full", [])
            diff = self._build_diff(None, files)
            diff["changedFileCount"] = len(diff["added"]) + len(diff["changed"]) + len(diff["deleted"])
            return folders, files, diff

        previous_files_by_path = dict((previous_snapshot.metadata or {}).get("filesByPath") or {})
        current_files_by_path = dict(previous_files_by_path)
        diff = self._collect_git_diff(root, previous_snapshot, git_context)

        for deleted_path in diff["deleted"]:
            current_files_by_path.pop(deleted_path, None)

        for old_path, new_path in diff["renamed"]:
            current_files_by_path.pop(old_path, None)
            file_path = root / new_path
            if file_path.exists() and file_path.is_file():
                current_files_by_path[new_path] = self._file_record(root, file_path.resolve())

        for path in sorted(set(diff["added"]) | set(diff["changed"])):
            file_path = root / path
            if file_path.exists() and file_path.is_file():
                current_files_by_path[path] = self._file_record(root, file_path.resolve())

        files = [current_files_by_path[path] for path in sorted(current_files_by_path)]
        folders = self._folders_from_files(files)
        diff["changedFileCount"] = len(diff["added"]) + len(diff["changed"]) + len(diff["deleted"]) + len(diff["renamed"])
        return folders, files, diff

    def _collect_structure(self, root: Path, mode: str, manual_paths: list[str]) -> tuple[list[str], list[dict[str, object]]]:
        resolved_root = root.resolve()
        selected_roots = self._selected_roots(resolved_root, mode, manual_paths)
        folders: set[str] = set()
        files: list[dict[str, object]] = []
        visited_dirs: set[str] = set()
        for selected_root in selected_roots:
            if selected_root.is_file():
                relative = selected_root.resolve().relative_to(resolved_root).as_posix()
                parent = Path(relative).parent.as_posix()
                if parent != ".":
                    folders.add(parent)
                files.append(self._file_record(resolved_root, selected_root.resolve()))
                continue
            for current_root, dirnames, filenames in os.walk(selected_root):
                current_path = Path(current_root).resolve()
                relative_dir = "." if current_path == resolved_root else current_path.relative_to(resolved_root).as_posix()
                if relative_dir not in visited_dirs:
                    folders.add(relative_dir)
                    visited_dirs.add(relative_dir)
                dirnames[:] = [
                    name
                    for name in dirnames
                    if name != ".git" and not Path(current_root, name).is_symlink()
                ]
                for name in filenames:
                    file_path = (current_path / name).resolve()
                    if file_path.is_symlink():
                        continue
                    files.append(self._file_record(resolved_root, file_path))
        files.sort(key=lambda item: str(item["path"]))
        normalized_folders = sorted(folder for folder in folders if folder and folder != ".")
        return normalized_folders, files

    def _selected_roots(self, root: Path, mode: str, manual_paths: list[str]) -> list[Path]:
        if mode != "Manual" or not manual_paths:
            return [root]
        selected: list[Path] = []
        for manual_path in manual_paths:
            candidate = (root / manual_path).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if candidate.exists():
                selected.append(candidate)
        return selected or [root]

    def _file_record(self, root: Path, file_path: Path) -> dict[str, object]:
        resolved_root = root.resolve()
        resolved_file_path = file_path.resolve()
        stat = resolved_file_path.stat()
        suffix = resolved_file_path.suffix.lower().lstrip(".")
        language = self._detect_language(suffix)
        relative_path = resolved_file_path.relative_to(resolved_root).as_posix()
        file_hash = hashlib.sha1(
            f"{relative_path}:{int(stat.st_mtime)}:{stat.st_size}".encode("utf-8")
        ).hexdigest()[:16]
        record = RepositoryFile(
            file_id=generated_id("repository_file"),
            repository_id="",
            path=relative_path,
            language=language,
            extension=suffix,
            size=int(stat.st_size),
            content_hash=file_hash,
            last_modified=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            metadata={},
        )
        return record.to_dict()

    def _build_snapshot(
        self,
        repository: Repository,
        mode: str,
        folders: list[str],
        files: list[dict[str, object]],
        diff: dict[str, object],
        git_context: dict[str, str],
    ) -> RepositorySnapshot:
        repository_id = repository.repository_id
        previous_version = self._latest_snapshot_version(repository_id)
        extensions: dict[str, int] = {}
        languages: dict[str, int] = {}
        total_size = 0
        files_by_path: dict[str, dict[str, object]] = {}
        modules: set[str] = set()
        for item in files:
            extension = str(item.get("extension") or "").lower()
            language = str(item.get("language") or RepositoryLanguage.UNKNOWN.value)
            path = str(item.get("path") or "")
            extensions[extension] = extensions.get(extension, 0) + 1
            languages[language] = languages.get(language, 0) + 1
            total_size += int(item.get("size") or 0)
            files_by_path[path] = item
            module = path.split("/", 1)[0] if "/" in path else path
            if module:
                modules.add(module)
        return RepositorySnapshot(
            snapshot_id=generated_id("snapshot"),
            repository_id=repository_id,
            version=previous_version + 1,
            created_at=now_iso(),
            branch=str(
                repository.metadata.get("branch")
                or git_context.get("branch")
                or repository.default_branch
                or "main"
            ),
            commit_id=str(
                repository.metadata.get("commitId")
                or repository.metadata.get("commitSha")
                or git_context.get("commitId")
                or ""
            ),
            total_files=len(files),
            languages=languages,
            modules=sorted(modules),
            status="Completed",
            summary=f"{mode} scan captured {len(files)} files across {len(folders)} folders.",
            scan_mode=mode,
            metadata={
                "folders": folders,
                "files": files,
                "extensions": extensions,
                "languages": languages,
                "totalFiles": len(files),
                "totalFolders": len(folders),
                "totalSize": total_size,
                "filesByPath": files_by_path,
                "diff": diff,
                "changedFileCount": int(diff.get("changedFileCount") or 0),
            },
        )

    def _build_diff(self, previous_snapshot: RepositorySnapshot | None, files: list[dict[str, object]]) -> dict[str, object]:
        previous = dict((previous_snapshot.metadata or {}).get("filesByPath") or {}) if previous_snapshot else {}
        current = {str(item.get("path")): item for item in files}
        added = sorted(path for path in current if path not in previous)
        deleted = sorted(path for path in previous if path not in current)
        changed = sorted(
            path
            for path, item in current.items()
            if path in previous
            and (
                item.get("contentHash") != previous[path].get("contentHash")
                or item.get("lastModified") != previous[path].get("lastModified")
                or item.get("size") != previous[path].get("size")
            )
        )
        unchanged = sorted(path for path in current if path in previous and path not in changed)
        return {
            "added": added,
            "changed": changed,
            "deleted": deleted,
            "renamed": [],
            "unchanged": unchanged,
        }

    def _collect_git_diff(
        self,
        root: Path,
        previous_snapshot: RepositorySnapshot,
        git_context: dict[str, str],
    ) -> dict[str, object]:
        if not git_context.get("isRepo"):
            return {"added": [], "changed": [], "deleted": [], "renamed": [], "unchanged": []}
        base_ref = previous_snapshot.commit_id or "HEAD"
        result = self._run_git_diff(root, base_ref)
        if result.returncode != 0 and base_ref != "HEAD":
            result = self._run_git_diff(root, "HEAD")
        if result.returncode != 0:
            return {"added": [], "changed": [], "deleted": [], "renamed": [], "unchanged": []}
        added: list[str] = []
        changed: list[str] = []
        deleted: list[str] = []
        renamed: list[tuple[str, str]] = []
        touched_paths: set[str] = set()
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("\t")
            status = parts[0]
            code = status[0]
            if code == "R" and len(parts) >= 3:
                old_path = parts[1]
                new_path = parts[2]
                renamed.append((old_path, new_path))
                touched_paths.add(new_path)
                continue
            if len(parts) < 2:
                continue
            path = parts[1]
            touched_paths.add(path)
            if code == "A":
                added.append(path)
            elif code in {"M", "T"}:
                changed.append(path)
            elif code == "D":
                deleted.append(path)
        previous = dict((previous_snapshot.metadata or {}).get("filesByPath") or {})
        current_paths = set(previous)
        current_paths -= set(deleted)
        current_paths -= {old for old, _new in renamed}
        current_paths |= set(added)
        current_paths |= set(changed)
        current_paths |= {new for _old, new in renamed}
        unchanged = sorted(path for path in current_paths if path not in touched_paths and path not in {new for _old, new in renamed})
        return {
            "added": sorted(added),
            "changed": sorted(changed),
            "deleted": sorted(deleted),
            "renamed": [[old, new] for old, new in sorted(renamed)],
            "unchanged": unchanged,
        }

    def _run_git_diff(self, root: Path, base_ref: str) -> subprocess.CompletedProcess:
        command = ["git", "-C", str(root), "diff", "--name-status", "--find-renames", base_ref]
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def _folders_from_files(self, files: list[dict[str, object]]) -> list[str]:
        folders: set[str] = set()
        for item in files:
            path = str(item.get("path") or "")
            if not path:
                continue
            parent = Path(path).parent.as_posix()
            if parent and parent != ".":
                folders.add(parent)
        return sorted(folders)

    def _get_latest_snapshot(self, repository_id: str) -> RepositorySnapshot | None:
        snapshots = [
            RepositorySnapshot.from_dict(item)
            for item in self._snapshot_store.read()
            if str(item.get("repositoryId") or item.get("repository_id")) == repository_id
        ]
        return snapshots[-1] if snapshots else None

    def _latest_snapshot_version(self, repository_id: str) -> int:
        latest = self._get_latest_snapshot(repository_id)
        return latest.version if latest else 0

    def _update_scan(
        self,
        scan: RepositoryScan,
        *,
        status: str,
        message: str,
        started_at: str = "",
        completed_at: str = "",
        progress: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RepositoryScan:
        updated = RepositoryScan.from_dict(
            {
                **scan.to_dict(),
                "status": status,
                "message": message,
                "startedAt": started_at or scan.started_at,
                "completedAt": completed_at or scan.completed_at,
                "progress": progress or scan.progress,
                "metadata": metadata or scan.metadata,
            }
        )
        self._save_scan(updated)
        return updated

    def _save_scan(self, scan: RepositoryScan) -> None:
        items = [RepositoryScan.from_dict(item) for item in self._store.read()]
        items = [item for item in items if item.repository_id != scan.repository_id]
        items.append(scan)
        self._store.write([item.to_dict() for item in items])

    def _empty_snapshot(self, repository_id: str, mode: str) -> RepositorySnapshot:
        return RepositorySnapshot(
            snapshot_id=generated_id("snapshot"),
            repository_id=repository_id,
            version=self._latest_snapshot_version(repository_id) + 1,
            created_at=now_iso(),
            status="Failed",
            summary="No scan results captured.",
            scan_mode=mode,
            metadata={},
        )

    def _detect_git_context(self, root: Path) -> dict[str, str]:
        if not root.exists():
            return {"isRepo": ""}
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip() != "true":
            return {"isRepo": ""}
        branch_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        commit_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "isRepo": "true",
            "branch": branch_result.stdout.strip() if branch_result.returncode == 0 else "",
            "commitId": commit_result.stdout.strip() if commit_result.returncode == 0 else "",
        }

    def _detect_language(self, extension: str) -> RepositoryLanguage:
        mapping = {
            "py": RepositoryLanguage.PYTHON,
            "ts": RepositoryLanguage.TYPESCRIPT,
            "tsx": RepositoryLanguage.TYPESCRIPT,
            "js": RepositoryLanguage.JAVASCRIPT,
            "jsx": RepositoryLanguage.JAVASCRIPT,
            "cs": RepositoryLanguage.CSHARP,
            "java": RepositoryLanguage.JAVA,
            "kt": RepositoryLanguage.KOTLIN,
            "swift": RepositoryLanguage.SWIFT,
            "dart": RepositoryLanguage.DART,
            "go": RepositoryLanguage.GO,
            "rs": RepositoryLanguage.RUST,
            "sql": RepositoryLanguage.SQL,
            "xml": RepositoryLanguage.XML,
            "xaml": RepositoryLanguage.XAML,
            "yaml": RepositoryLanguage.YAML,
            "yml": RepositoryLanguage.YAML,
            "json": RepositoryLanguage.JSON,
            "md": RepositoryLanguage.MARKDOWN,
        }
        return mapping.get(extension.lower(), RepositoryLanguage.UNKNOWN)
