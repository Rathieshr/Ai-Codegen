"""Repository Context Capsule builder."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..domain import (
    EngineeringGraph,
    EngineeringNodeType,
    RepositoryContextCapsule,
    RepositoryFileRanking,
    RepositorySnapshot,
)


class RepositoryContextCapsuleBuilder:
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
        snapshot = repository_snapshot.to_dict() if isinstance(repository_snapshot, RepositorySnapshot) else dict(repository_snapshot or {})
        graph = engineering_graph.to_dict() if isinstance(engineering_graph, EngineeringGraph) else dict(engineering_graph or {})
        query_terms = _query_terms(story, selected_modules or [], selected_flows or [])
        ranked_files = _normalize_rankings(repository_ranking)
        graph_index = _GraphLookup(graph)

        relevant_files = self._select_relevant_files(ranked_files, query_terms)
        relevant_apis = self._select_relevant_apis(graph_index, query_terms, relevant_files)
        dependencies = self._select_dependencies(graph_index, relevant_files, relevant_apis)
        module_context = self._build_module_context(graph_index, relevant_files, relevant_apis, selected_modules or [])
        architecture_rules = self._architecture_rules(snapshot, selected_modules or [], selected_flows or [])
        risks = self._risks(story, relevant_files, relevant_apis, snapshot, selected_modules or [])
        suggested_tests = self._suggested_tests(story, selected_flows or [], relevant_apis, dependencies)
        graph_references = self._graph_references(graph_index, relevant_files, relevant_apis)

        return RepositoryContextCapsule(
            story_title=_clean(story.get("title") or "Approved Story"),
            relevant_files=relevant_files,
            relevant_apis=relevant_apis,
            dependencies=dependencies,
            architecture_rules=architecture_rules,
            risks=risks,
            suggested_tests=suggested_tests,
            module_context=module_context,
            graph_references=graph_references,
            diagnostics={
                "snapshotId": _clean(snapshot.get("snapshotId") or snapshot.get("snapshot_id")),
                "snapshotVersion": snapshot.get("version") or "",
                "graphId": _clean(graph.get("graphId") or graph.get("graph_id")),
                "queryTerms": sorted(query_terms),
                "rankingCandidates": len(ranked_files),
                "selectedFileCount": len(relevant_files),
                "selectedApiCount": len(relevant_apis),
                "selectedDependencyCount": len(dependencies),
                "selectedModuleCount": len(module_context),
            },
        )

    def _select_relevant_files(self, ranked_files: list[dict[str, Any]], query_terms: set[str]) -> list[dict[str, Any]]:
        if not ranked_files:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in ranked_files:
            path = _clean(item.get("path"))
            evidence_text = " ".join([path, _clean(item.get("reason")), _clean(item.get("evidence")), " ".join(_string_list(item.get("dependencies")))])
            overlap = len(query_terms & _keywords(evidence_text))
            base = float(item.get("confidence") or 0.0)
            score = base + overlap * 0.08
            scored.append(
                (
                    score,
                    {
                        "path": path,
                        "confidence": round(min(0.99, max(base, 0.55 + overlap * 0.07)), 2),
                        "reason": _clean(item.get("reason")) or "Repository file matched the approved story intent.",
                        "evidence": _clean(item.get("evidence")) or path,
                        "dependencies": _string_list(item.get("dependencies")),
                        "source": _clean(item.get("source")) or "repository_ranking",
                    },
                )
            )
        scored.sort(key=lambda entry: (-entry[0], entry[1]["path"]))
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _score, item in scored:
            if item["path"] in seen:
                continue
            seen.add(item["path"])
            selected.append(item)
            if len(selected) >= 8:
                break
        return selected

    def _select_relevant_apis(
        self,
        graph_index: "_GraphLookup",
        query_terms: set[str],
        relevant_files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        file_paths = {item["path"] for item in relevant_files}
        apis: list[tuple[float, dict[str, Any]]] = []
        for node in graph_index.nodes_by_type.get(EngineeringNodeType.API.value, []) + graph_index.nodes_by_type.get(EngineeringNodeType.CONTROLLER.value, []):
            node_terms = _keywords(" ".join([_clean(node.get("name")), _clean(node.get("path")), _clean(node.get("metadata"))]))
            overlap = len(query_terms & node_terms)
            connected_paths = {neighbor.get("path") for neighbor in graph_index.neighbors(node["nodeId"]) if _clean(neighbor.get("path"))}
            connected_match = len(file_paths & connected_paths)
            if not overlap and not connected_match:
                continue
            reason_parts = []
            if overlap:
                reason_parts.append(f"matched {', '.join(sorted(query_terms & node_terms)[:3])}")
            if connected_match:
                reason_parts.append("connected to ranked files")
            apis.append(
                (
                    overlap * 1.5 + connected_match * 1.2 + 0.5,
                    {
                        "name": _clean(node.get("name")) or Path(_clean(node.get("path"))).stem,
                        "path": _clean(node.get("path")),
                        "type": _clean(node.get("nodeType")) or "API",
                        "confidence": round(min(0.98, 0.58 + overlap * 0.08 + connected_match * 0.1), 2),
                        "reason": " and ".join(reason_parts) or "Selected from engineering graph.",
                        "evidence": [_clean(node.get("path")) or _clean(node.get("name"))],
                        "source": "engineering_graph",
                    },
                )
            )
        apis.sort(key=lambda entry: (-entry[0], entry[1]["name"]))
        return [item for _score, item in apis[:6]]

    def _select_dependencies(
        self,
        graph_index: "_GraphLookup",
        relevant_files: list[dict[str, Any]],
        relevant_apis: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        dependencies: dict[str, dict[str, Any]] = {}
        node_ids = list(graph_index.node_ids_for_paths(item["path"]) for item in relevant_files)
        api_names = {_clean(item.get("name")) for item in relevant_apis}
        flattened_ids = {node_id for group in node_ids for node_id in group}
        for node_id in flattened_ids:
            for neighbor in graph_index.neighbors(node_id):
                name = _clean(neighbor.get("name"))
                node_type = _clean(neighbor.get("nodeType")) or "Dependency"
                if not name or name in api_names or node_type == EngineeringNodeType.FILE.value:
                    continue
                entry = dependencies.setdefault(
                    name.casefold(),
                    {
                        "name": name,
                        "type": node_type,
                        "confidence": 0.62,
                        "reason": f"Connected through engineering graph from ranked repository files.",
                        "evidence": [],
                        "source": "engineering_graph",
                    },
                )
                evidence = _clean(neighbor.get("path")) or name
                if evidence and evidence not in entry["evidence"]:
                    entry["evidence"].append(evidence)
                entry["confidence"] = min(0.96, float(entry["confidence"]) + 0.08)
        return list(dependencies.values())[:10]

    def _build_module_context(
        self,
        graph_index: "_GraphLookup",
        relevant_files: list[dict[str, Any]],
        relevant_apis: list[dict[str, Any]],
        selected_modules: list[str],
    ) -> list[dict[str, Any]]:
        module_map: dict[str, dict[str, Any]] = {}
        selected_lower = {item.casefold() for item in selected_modules}
        for module in graph_index.nodes_by_type.get(EngineeringNodeType.MODULE.value, []):
            name = _clean(module.get("name"))
            if not name:
                continue
            module_map[name.casefold()] = {
                "name": name,
                "confidence": 0.68 if name.casefold() in selected_lower else 0.55,
                "files": [],
                "apis": [],
                "services": [],
                "reason": "Selected by repository structure.",
                "source": "engineering_graph",
            }

        for file_entry in relevant_files:
            path = file_entry["path"]
            module_name = path.split("/", 1)[0] if "/" in path else path
            key = module_name.casefold()
            module = module_map.setdefault(
                key,
                {
                    "name": module_name,
                    "confidence": 0.6,
                    "files": [],
                    "apis": [],
                    "services": [],
                    "reason": "Derived from ranked repository file paths.",
                    "source": "repository_ranking",
                },
            )
            if path not in module["files"]:
                module["files"].append(path)
            module["confidence"] = min(0.98, float(module["confidence"]) + 0.08)

        for api_entry in relevant_apis:
            path = _clean(api_entry.get("path"))
            module_name = path.split("/", 1)[0] if "/" in path else ""
            if not module_name:
                continue
            module = module_map.setdefault(
                module_name.casefold(),
                {
                    "name": module_name,
                    "confidence": 0.62,
                    "files": [],
                    "apis": [],
                    "services": [],
                    "reason": "Derived from relevant API path.",
                    "source": "engineering_graph",
                },
            )
            if api_entry["name"] not in module["apis"]:
                module["apis"].append(api_entry["name"])
            module["confidence"] = min(0.98, float(module["confidence"]) + 0.06)

        ordered = sorted(module_map.values(), key=lambda item: (-float(item["confidence"]), item["name"]))
        return ordered[:6]

    def _architecture_rules(self, snapshot: dict[str, Any], selected_modules: list[str], selected_flows: list[str]) -> list[str]:
        rules: list[str] = []
        metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        for note in _string_list(metadata.get("architectureNotes"))[:4]:
            rules.append(note)
        if selected_modules:
            rules.append(f"Keep implementation inside the selected modules: {', '.join(selected_modules[:4])}.")
        if selected_flows:
            rules.append(f"Preserve flow behavior for {', '.join(selected_flows[:3])}.")
        if snapshot.get("scanMode"):
            rules.append(f"Use repository evidence from the {snapshot.get('scanMode')} snapshot only.")
        return _unique(rules)[:6]

    def _risks(
        self,
        story: dict[str, object],
        relevant_files: list[dict[str, Any]],
        relevant_apis: list[dict[str, Any]],
        snapshot: dict[str, Any],
        selected_modules: list[str],
    ) -> list[str]:
        text = " ".join(
            [
                _clean(story.get("title")),
                _clean(story.get("description")),
                " ".join(_string_list(story.get("acceptance_criteria"))),
            ]
        ).casefold()
        risks: list[str] = []
        if not relevant_files:
            risks.append("Repository file ranking is limited; verify target files before implementation.")
        if not relevant_apis and any(term in text for term in ["api", "endpoint", "service", "device", "fault"]):
            risks.append("API context is incomplete; confirm the integration surface before coding.")
        if "permission" in text or "access" in text or "role" in text:
            risks.append("Authorization paths must be validated for role-based access.")
        if "refresh" in text or "duplicate" in text:
            risks.append("Refresh behavior must prevent duplicate records or stale state.")
        if selected_modules and not snapshot.get("modules"):
            risks.append("Snapshot module metadata is incomplete; confirm module ownership before implementation.")
        return _unique(risks)[:6]

    def _suggested_tests(
        self,
        story: dict[str, object],
        selected_flows: list[str],
        relevant_apis: list[dict[str, Any]],
        dependencies: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        title = _clean(story.get("title") or "approved behavior")
        flow = selected_flows[0] if selected_flows else "approved flow"
        dependency_names = [item["name"] for item in dependencies[:2] if _clean(item.get("name"))]
        tests = [
            {
                "type": "unit",
                "title": f"Validate {title} business rules",
                "reason": "Core behavior should stay inside the approved implementation boundary.",
            },
            {
                "type": "integration",
                "title": f"Verify {flow} integration behavior",
                "reason": "Repository context indicates flow-level integration impact.",
            },
            {
                "type": "negative",
                "title": f"Handle missing or invalid data for {title}",
                "reason": "Story context includes operational failure handling.",
            },
        ]
        if relevant_apis:
            tests.append(
                {
                    "type": "api",
                    "title": f"Validate {' / '.join(item['name'] for item in relevant_apis[:2])} contract behavior",
                    "reason": "Relevant APIs were selected from the engineering graph.",
                }
            )
        if dependency_names:
            tests.append(
                {
                    "type": "regression",
                    "title": f"Regression check for {', '.join(dependency_names)}",
                    "reason": "Dependencies connected to ranked files may regress.",
                }
            )
        return tests[:6]

    def _graph_references(
        self,
        graph_index: "_GraphLookup",
        relevant_files: list[dict[str, Any]],
        relevant_apis: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for item in relevant_files[:4]:
            for node in graph_index.nodes_for_path(item["path"]):
                references.append(
                    {
                        "nodeId": _clean(node.get("nodeId")),
                        "nodeType": _clean(node.get("nodeType")),
                        "name": _clean(node.get("name")),
                        "path": _clean(node.get("path")),
                        "source": "engineering_graph",
                    }
                )
        for item in relevant_apis[:3]:
            path = _clean(item.get("path"))
            if not path:
                continue
            for node in graph_index.nodes_for_path(path):
                references.append(
                    {
                        "nodeId": _clean(node.get("nodeId")),
                        "nodeType": _clean(node.get("nodeType")),
                        "name": _clean(node.get("name")),
                        "path": _clean(node.get("path")),
                        "source": "engineering_graph",
                    }
                )
        return references[:10]


class _GraphLookup:
    def __init__(self, graph: dict[str, Any]) -> None:
        self.nodes = [node for node in list(graph.get("nodes") or []) if isinstance(node, dict)]
        self.relationships = [item for item in list(graph.get("relationships") or []) if isinstance(item, dict)]
        self.nodes_by_id = {_clean(node.get("nodeId")): node for node in self.nodes if _clean(node.get("nodeId"))}
        self.nodes_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.nodes_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.neighbors_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in self.nodes:
            node_type = _clean(node.get("nodeType"))
            if node_type:
                self.nodes_by_type[node_type].append(node)
            path = _clean(node.get("path"))
            if path:
                self.nodes_by_path[path].append(node)
        for relationship in self.relationships:
            from_id = _clean(relationship.get("fromNodeId"))
            to_id = _clean(relationship.get("toNodeId"))
            if from_id and to_id:
                to_node = self.nodes_by_id.get(to_id)
                from_node = self.nodes_by_id.get(from_id)
                if to_node:
                    self.neighbors_by_id[from_id].append(to_node)
                if from_node:
                    self.neighbors_by_id[to_id].append(from_node)

    def neighbors(self, node_id: str) -> list[dict[str, Any]]:
        return list(self.neighbors_by_id.get(_clean(node_id), []))

    def nodes_for_path(self, path: str) -> list[dict[str, Any]]:
        return list(self.nodes_by_path.get(_clean(path), []))

    def node_ids_for_paths(self, path: str) -> list[str]:
        return [_clean(node.get("nodeId")) for node in self.nodes_for_path(path) if _clean(node.get("nodeId"))]


def _normalize_rankings(values: list[RepositoryFileRanking | dict[str, object] | str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, RepositoryFileRanking):
            normalized.append(
                {
                    "path": item.path,
                    "confidence": item.confidence,
                    "reason": item.reason,
                    "dependencies": list(item.dependencies),
                    "evidence": item.metadata.get("evidence") if isinstance(item.metadata, dict) else "",
                    "source": "repository_intelligence",
                }
            )
        elif isinstance(item, dict):
            path = _clean(item.get("path") or item.get("file") or item.get("name"))
            if not path:
                continue
            normalized.append(
                {
                    "path": path,
                    "confidence": float(item.get("confidence") or item.get("score") or 0.0),
                    "reason": _clean(item.get("reason")),
                    "dependencies": _string_list(item.get("dependencies")),
                    "evidence": item.get("evidence") or "",
                    "source": _clean(item.get("source")) or "repository_intelligence",
                }
            )
        else:
            path = _clean(item)
            if path:
                normalized.append(
                    {
                        "path": path,
                        "confidence": 0.55,
                        "reason": "Repository source file matched the approved story context.",
                        "dependencies": [],
                        "evidence": path,
                        "source": "repository_intelligence",
                    }
                )
    return normalized


def _query_terms(story: dict[str, object], modules: list[str], flows: list[str]) -> set[str]:
    source = " ".join(
        [
            _clean(story.get("title")),
            _clean(story.get("description")),
            " ".join(_string_list(story.get("acceptance_criteria"))),
            " ".join(modules),
            " ".join(flows),
        ]
    )
    return _keywords(source)


def _keywords(text: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9#]+", text.casefold()) if len(part) >= 3}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _unique([part.strip() for part in re.split(r"[\n,]", value) if part.strip()])
    if isinstance(value, dict):
        return _unique([_clean(value.get("name") or value.get("path") or value.get("title"))])
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_string_list(item))
        return _unique([item for item in result if item])
    cleaned = _clean(value)
    return [cleaned] if cleaned else []


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result
