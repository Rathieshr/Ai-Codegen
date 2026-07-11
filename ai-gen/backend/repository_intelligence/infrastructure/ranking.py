"""Repository file ranking service."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.engineering_memory.engine import EngineeringMemoryEngine

from ..domain import (
    EngineeringGraph,
    EngineeringNodeType,
    IEngineeringGraphService,
    ISnapshotService,
    Repository,
    RepositoryFileRanking,
    RepositorySnapshot,
    RelationshipType,
)


class FileBackedRepositoryFileRankingService:
    def __init__(
        self,
        graph_service: IEngineeringGraphService,
        snapshot_service: ISnapshotService,
        memory_engine: EngineeringMemoryEngine,
    ) -> None:
        self.graph_service = graph_service
        self.snapshot_service = snapshot_service
        self.memory_engine = memory_engine

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
        graph = self.graph_service.get_graph(repository.repository_id)
        snapshot = self.snapshot_service.get_latest_snapshot(repository.repository_id)
        if not graph or not snapshot:
            return []

        query_terms = _build_query_terms(
            artifact_type=artifact_type,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria or [],
            tags=tags or [],
            selected_modules=selected_modules or [],
            selected_flows=selected_flows or [],
        )
        if not query_terms:
            return []

        scores: dict[str, float] = defaultdict(float)
        reasons: dict[str, list[str]] = defaultdict(list)
        dependencies: dict[str, set[str]] = defaultdict(set)
        files_by_path = {
            str(item.get("path") or ""): item
            for item in list((snapshot.metadata or {}).get("files") or [])
            if str(item.get("path") or "")
        }
        graph_index = _GraphIndex(graph)

        self._score_file_metadata(query_terms, files_by_path, scores, reasons)
        self._score_modules(query_terms, graph_index, scores, reasons, dependencies)
        self._score_graph_nodes(query_terms, graph_index, scores, reasons, dependencies)
        self._score_memory(repository, query_terms, scores, reasons, dependencies)

        ranked: list[RepositoryFileRanking] = []
        max_score = max(scores.values(), default=0.0)
        for path, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
            if path not in files_by_path or score <= 0:
                continue
            confidence = _to_confidence(score, max_score)
            ranked.append(
                RepositoryFileRanking(
                    path=path,
                    confidence=confidence,
                    reason="; ".join(_unique_preserve_order(reasons.get(path, []))[:3]),
                    dependencies=sorted(dependencies.get(path, set())),
                    metadata={
                        "artifactType": artifact_type,
                        "language": str(files_by_path[path].get("language") or ""),
                        "extension": str(files_by_path[path].get("extension") or ""),
                        "score": round(score, 4),
                    },
                )
            )
            if len(ranked) >= max(1, int(limit or 10)):
                break
        return ranked

    def _score_file_metadata(
        self,
        query_terms: set[str],
        files_by_path: dict[str, dict[str, Any]],
        scores: dict[str, float],
        reasons: dict[str, list[str]],
    ) -> None:
        for path, file_record in files_by_path.items():
            path_terms = _path_terms(path)
            overlap = query_terms & path_terms
            if overlap:
                scores[path] += 2.5 + len(overlap) * 1.2
                reasons[path].append(f"path matched {', '.join(sorted(overlap)[:3])}")
            language = str(file_record.get("language") or "").lower()
            if language and language in query_terms:
                scores[path] += 0.8
                reasons[path].append(f"language matched {language}")

    def _score_modules(
        self,
        query_terms: set[str],
        graph_index: "_GraphIndex",
        scores: dict[str, float],
        reasons: dict[str, list[str]],
        dependencies: dict[str, set[str]],
    ) -> None:
        for module_node in graph_index.nodes_by_type.get(EngineeringNodeType.MODULE.value, []):
            module_terms = _tokenize(f"{module_node['name']} {module_node.get('path') or ''}")
            overlap = query_terms & module_terms
            if not overlap:
                continue
            file_nodes = graph_index.outgoing(module_node["nodeId"], RelationshipType.CONTAINS.value)
            for file_node in file_nodes:
                if file_node.get("nodeType") != EngineeringNodeType.FILE.value:
                    continue
                path = str(file_node.get("path") or "")
                if not path:
                    continue
                scores[path] += 3.0 + len(overlap) * 0.8
                reasons[path].append(f"module {module_node['name']} matched {', '.join(sorted(overlap)[:3])}")
                dependencies[path].add(module_node["name"])

    def _score_graph_nodes(
        self,
        query_terms: set[str],
        graph_index: "_GraphIndex",
        scores: dict[str, float],
        reasons: dict[str, list[str]],
        dependencies: dict[str, set[str]],
    ) -> None:
        relevant_types = {
            EngineeringNodeType.CONTROLLER.value,
            EngineeringNodeType.SERVICE.value,
            EngineeringNodeType.REPOSITORY.value,
            EngineeringNodeType.API.value,
            EngineeringNodeType.DTO.value,
            EngineeringNodeType.TEST.value,
            EngineeringNodeType.UI.value,
            EngineeringNodeType.FILE.value,
        }
        for node in graph_index.nodes:
            if node.get("nodeType") not in relevant_types:
                continue
            node_terms = _tokenize(f"{node.get('name') or ''} {node.get('path') or ''} {node.get('metadata', {})}")
            overlap = query_terms & node_terms
            if not overlap:
                continue
            path = str(node.get("path") or "")
            if node.get("nodeType") == EngineeringNodeType.FILE.value and path:
                scores[path] += 2.0 + len(overlap) * 1.4
                reasons[path].append(f"file identity matched {', '.join(sorted(overlap)[:3])}")
            elif path:
                scores[path] += 4.0 + len(overlap) * 1.1
                reasons[path].append(f"{node['nodeType']} {node['name']} matched {', '.join(sorted(overlap)[:3])}")
                dependencies[path].add(node["name"])

            for related_node in graph_index.neighbors(node["nodeId"]):
                related_path = str(related_node.get("path") or "")
                if related_node.get("nodeType") in {EngineeringNodeType.FILE.value, EngineeringNodeType.UI.value} and related_path:
                    scores[related_path] += 1.7
                    reasons[related_path].append(f"connected to {node['nodeType']} {node['name']}")
                    dependencies[related_path].add(node["name"])
                elif related_path:
                    scores[related_path] += 0.9
                    reasons[related_path].append(f"dependency from {node['name']}")
                    dependencies[related_path].add(node["name"])

    def _score_memory(
        self,
        repository: Repository,
        query_terms: set[str],
        scores: dict[str, float],
        reasons: dict[str, list[str]],
        dependencies: dict[str, set[str]],
    ) -> None:
        memory_query = {
            "projectId": repository.project_id or "default",
            "query": sorted(query_terms),
            "repository": [repository.name],
            "limit": 10,
        }
        result = self.memory_engine.find_relevant_memory(memory_query)
        for memory in list(result.get("results") or []):
            weight = 2.0 + float(memory.get("confidence") or 0.0) * 2.0
            title = str(memory.get("title") or memory.get("summary") or "Engineering Memory")
            for evidence in list(memory.get("repositoryEvidence") or []):
                path = self._memory_path(evidence)
                if not path:
                    continue
                scores[path] += weight
                reasons[path].append(f"memory matched {title}")
                dependencies[path].add(title)
            for reference in list(memory.get("graphReferences") or []):
                path = str(reference or "").strip()
                if "/" not in path or "." not in path:
                    continue
                scores[path] += max(1.0, weight - 0.5)
                reasons[path].append(f"graph reference from memory {title}")
                dependencies[path].add(title)

    def _memory_path(self, evidence: Any) -> str:
        if isinstance(evidence, dict):
            return str(evidence.get("path") or evidence.get("file") or "").strip()
        text = str(evidence or "").strip()
        if "/" in text and "." in text:
            return text
        return ""


class _GraphIndex:
    def __init__(self, graph: EngineeringGraph) -> None:
        self.nodes = [node.to_dict() for node in graph.nodes]
        self.relationships = [relationship.to_dict() for relationship in graph.relationships]
        self.node_by_id = {node["nodeId"]: node for node in self.nodes}
        self.nodes_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in self.nodes:
            self.nodes_by_type[str(node.get("nodeType") or "")].append(node)
        for relationship in self.relationships:
            self._outgoing[str(relationship.get("fromNodeId") or "")].append(relationship)
            self._incoming[str(relationship.get("toNodeId") or "")].append(relationship)

    def outgoing(self, node_id: str, relationship_type: str = "") -> list[dict[str, Any]]:
        items = self._outgoing.get(node_id, [])
        if relationship_type:
            items = [item for item in items if item.get("relationshipType") == relationship_type]
        return [self.node_by_id[item["toNodeId"]] for item in items if item.get("toNodeId") in self.node_by_id]

    def neighbors(self, node_id: str) -> list[dict[str, Any]]:
        neighbors: list[dict[str, Any]] = []
        for item in self._outgoing.get(node_id, []):
            if item.get("toNodeId") in self.node_by_id:
                neighbors.append(self.node_by_id[item["toNodeId"]])
        for item in self._incoming.get(node_id, []):
            if item.get("fromNodeId") in self.node_by_id:
                neighbors.append(self.node_by_id[item["fromNodeId"]])
        return neighbors


def _build_query_terms(
    *,
    artifact_type: str,
    title: str,
    description: str,
    acceptance_criteria: list[str],
    tags: list[str],
    selected_modules: list[str],
    selected_flows: list[str],
) -> set[str]:
    parts = [
        artifact_type,
        title,
        description,
        *acceptance_criteria,
        *tags,
        *selected_modules,
        *selected_flows,
    ]
    return _tokenize(" ".join(part for part in parts if part))


def _tokenize(text: str) -> set[str]:
    raw = re.findall(r"[A-Za-z0-9_./-]+", str(text or ""))
    tokens: set[str] = set()
    for item in raw:
        value = item.strip().lower()
        if len(value) >= 3:
            tokens.add(value)
        for split in re.split(r"[^a-zA-Z0-9]+", item):
            normalized = split.strip().lower()
            if len(normalized) >= 3:
                tokens.add(normalized)
        for camel in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", item):
            normalized = camel.strip().lower()
            if len(normalized) >= 3:
                tokens.add(normalized)
    return tokens


def _path_terms(path: str) -> set[str]:
    parts = list(Path(path).parts)
    return _tokenize(" ".join(parts))


def _to_confidence(score: float, max_score: float) -> float:
    if max_score <= 0:
        return 0.0
    ratio = score / max_score
    return min(0.99, 0.35 + ratio * 0.64)


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
