from __future__ import annotations

import hashlib
from typing import Any

from .engineering_graph import EngineeringGraph
from .graph_edge import GraphEdge
from .graph_node import GraphNode


WORK_ITEM_TYPES = {"Epic", "Feature", "Story", "Task"}


class GraphBuilder:
    def build_engineering_graph(
        self,
        *,
        project_profile: dict[str, Any] | None = None,
        knowledge_registry: dict[str, Any] | None = None,
        repository_snapshot: dict[str, Any] | None = None,
        planning_artifacts: list[dict[str, Any]] | None = None,
        execution_artifacts: list[dict[str, Any]] | None = None,
        validation_reports: list[dict[str, Any]] | None = None,
        context_capsules: list[dict[str, Any]] | None = None,
    ) -> EngineeringGraph:
        graph = EngineeringGraph(metadata={"builder": "GraphBuilder"})
        project = _as_dict(project_profile)
        project_node = self._project_node(project)
        graph.add_node(project_node)

        self._add_repository_snapshot(graph, project_node.id, _as_dict(repository_snapshot))
        self._add_knowledge_registry(graph, project_node.id, _as_dict(knowledge_registry))
        self._add_planning_artifacts(graph, project_node.id, planning_artifacts or [])
        self._add_context_capsules(graph, context_capsules or [])
        self._add_execution_artifacts(graph, execution_artifacts or [])
        self._add_validation_reports(graph, validation_reports or [])
        return graph

    def _project_node(self, profile: dict[str, Any]) -> GraphNode:
        name = _first_text(profile, "project_name", "projectName", "name", "title") or "Project Intelligence"
        project_id = _first_text(profile, "project_id", "projectId", "id") or _stable_id("Project", name)
        return GraphNode(
            id=f"Project:{project_id}",
            type="Project",
            name=name,
            metadata=profile,
            source="manual" if profile else "knowledge_registry",
        )

    def _add_repository_snapshot(self, graph: EngineeringGraph, project_id: str, snapshot: dict[str, Any]) -> None:
        repo_name = _first_text(snapshot, "repository", "repository_name", "name")
        if repo_name:
            repo = graph.add_node(GraphNode(_stable_id("Repository", repo_name), "Repository", repo_name, snapshot, source="repository"))
            graph.add_edge(GraphEdge("", project_id, repo.id, "contains", source="repository"))
        for file_item in _items(snapshot.get("files") or snapshot.get("source_files") or snapshot.get("sourceFiles")):
            path = _item_name(file_item, "path", "file", "name")
            if not path:
                continue
            node = graph.add_node(GraphNode(_stable_id("File", path), "File", path, _as_dict(file_item), source="repository"))
            graph.add_edge(GraphEdge("", project_id, node.id, "references", source="repository"))

    def _add_knowledge_registry(self, graph: EngineeringGraph, project_id: str, registry: dict[str, Any]) -> None:
        mappings = [
            ("applications", "Application", "contains"),
            ("modules", "Module", "contains"),
            ("flows", "Flow", "contains"),
            ("components", "Service", "contains"),
            ("dependencies", "Dependency", "depends_on"),
            ("standards", "Standard", "references"),
        ]
        for key, node_type, edge_type in mappings:
            for item in _items(registry.get(key)):
                name = _item_name(item, "name", "title", "path")
                if not name:
                    continue
                node = graph.add_node(GraphNode(_stable_id(node_type, name), node_type, name, _as_dict(item), source="knowledge_registry"))
                graph.add_edge(GraphEdge("", project_id, node.id, edge_type, source="knowledge_registry"))

    def _add_planning_artifacts(self, graph: EngineeringGraph, project_id: str, artifacts: list[dict[str, Any]]) -> None:
        last_by_type: dict[str, str] = {"Project": project_id}
        for artifact in artifacts:
            artifact_type = _first_text(artifact, "type", "artifact_type", "artifactType", "work_item_type", "workItemType") or "Story"
            artifact_type = _canonical_type(artifact_type)
            if artifact_type not in WORK_ITEM_TYPES:
                artifact_type = "Story"
            node = graph.add_node(_artifact_node(artifact, artifact_type, "planning"))
            parent_id = _first_text(artifact, "parent_id", "parentId", "parent_work_item_id", "parentWorkItemId")
            parent_type = _canonical_type(_first_text(artifact, "parent_type", "parentType") or "")
            parent_node_id = _resolve_parent(graph, parent_id, parent_type) or _default_parent(last_by_type, artifact_type, project_id)
            if parent_node_id:
                graph.add_edge(GraphEdge("", parent_node_id, node.id, "contains", source="planning"))
                graph.add_edge(GraphEdge("", node.id, parent_node_id, "derives_from", source="planning"))
            last_by_type[artifact_type] = node.id
            self._link_artifact_context(graph, node.id, artifact, "planning")

    def _add_context_capsules(self, graph: EngineeringGraph, capsules: list[dict[str, Any]]) -> None:
        for capsule in capsules:
            name = _first_text(capsule, "capsuleId", "capsule_id", "title", "name") or "Context Capsule"
            node = graph.add_node(GraphNode(_stable_id("ContextCapsule", name), "ContextCapsule", name, capsule, source="execution"))
            source_id = _first_text(capsule, "sourceWorkItemId", "source_work_item_id", "parentStoryId", "parent_story_id")
            source_node = _find_work_item_by_external_id(graph, source_id)
            if source_node:
                graph.add_edge(GraphEdge("", node.id, source_node.id, "generated_from", source="execution"))
            self._link_named_refs(graph, node.id, capsule, "selectedModules", "Module", "uses", "execution")
            self._link_named_refs(graph, node.id, capsule, "selectedFlows", "Flow", "uses", "execution")
            self._link_named_refs(graph, node.id, capsule, "selectedDependencies", "Dependency", "depends_on", "execution")
            self._link_named_refs(graph, node.id, capsule, "selectedStandards", "Standard", "references", "execution")
            self._link_named_refs(graph, node.id, capsule, "relevantFiles", "File", "references", "repository")

    def _add_execution_artifacts(self, graph: EngineeringGraph, artifacts: list[dict[str, Any]]) -> None:
        for artifact in artifacts:
            name = _first_text(artifact, "title", "name", "artifact_id", "artifactId") or "Execution Package"
            node = graph.add_node(GraphNode(_stable_id("ExecutionPackage", name), "ExecutionPackage", name, artifact, source="execution"))
            capsule = _as_dict(artifact.get("context_capsule") or artifact.get("contextCapsule"))
            capsule_name = _first_text(capsule, "capsuleId", "capsule_id", "title", "name")
            if capsule_name:
                capsule_node = graph.add_node(GraphNode(_stable_id("ContextCapsule", capsule_name), "ContextCapsule", capsule_name, capsule, source="execution"))
                graph.add_edge(GraphEdge("", node.id, capsule_node.id, "generated_from", source="execution"))
            self._link_artifact_context(graph, node.id, artifact, "execution")

    def _add_validation_reports(self, graph: EngineeringGraph, reports: list[dict[str, Any]]) -> None:
        for report in reports:
            name = _first_text(report, "report_id", "reportId", "title", "name") or "Validation Report"
            node = graph.add_node(GraphNode(_stable_id("ValidationReport", name), "ValidationReport", name, report, source="validation"))
            source_id = _first_text(report, "sourceWorkItemId", "source_work_item_id", "work_item_id", "workItemId")
            source_node = _find_work_item_by_external_id(graph, source_id)
            if source_node:
                graph.add_edge(GraphEdge("", source_node.id, node.id, "validated_by", source="validation"))

    def _link_artifact_context(self, graph: EngineeringGraph, node_id: str, payload: dict[str, Any], source: str) -> None:
        self._link_named_refs(graph, node_id, payload, "capabilities", "Capability", "implements", source)
        self._link_named_refs(graph, node_id, payload, "personas", "Persona", "uses", source)
        self._link_named_refs(graph, node_id, payload, "business_goals", "BusinessGoal", "implements", source)
        self._link_named_refs(graph, node_id, payload, "modules", "Module", "uses", source)
        self._link_named_refs(graph, node_id, payload, "flows", "Flow", "uses", source)
        self._link_named_refs(graph, node_id, payload, "applications", "Application", "uses", source)
        self._link_named_refs(graph, node_id, payload, "dependencies", "Dependency", "depends_on", source)
        self._link_named_refs(graph, node_id, payload, "standards", "Standard", "references", source)
        self._link_named_refs(graph, node_id, payload, "rejected_context", "Module", "rejected", source)
        generated_using = _as_dict(payload.get("generatedUsing") or payload.get("generated_using"))
        if generated_using:
            self._link_artifact_context(graph, node_id, generated_using, source)

    def _link_named_refs(
        self,
        graph: EngineeringGraph,
        node_id: str,
        payload: dict[str, Any],
        key: str,
        node_type: str,
        edge_type: str,
        source: str,
    ) -> None:
        for item in _items(payload.get(key) or payload.get(_camel(key))):
            name = _item_name(item, "name", "title", "path")
            if not name:
                continue
            ref_node = graph.add_node(GraphNode(_stable_id(node_type, name), node_type, name, _as_dict(item), source=source))
            graph.add_edge(GraphEdge("", node_id, ref_node.id, edge_type, confidence=_confidence(item), source=source))


def _artifact_node(payload: dict[str, Any], artifact_type: str, source: str) -> GraphNode:
    title = _first_text(payload, "title", "name", "description") or artifact_type
    external_id = _first_text(payload, "id", "work_item_id", "workItemId", "azure_work_item_id", "azureWorkItemId")
    node_id = f"{artifact_type}:{external_id}" if external_id else _stable_id(artifact_type, title)
    return GraphNode(node_id, artifact_type, title, payload, confidence=_confidence(payload), source=source)


def _resolve_parent(graph: EngineeringGraph, parent_id: str, parent_type: str) -> str:
    if parent_id and parent_type:
        candidate = f"{parent_type}:{parent_id}"
        if candidate in graph.nodes:
            return candidate
    if parent_id:
        found = _find_work_item_by_external_id(graph, parent_id)
        return found.id if found else ""
    return ""


def _default_parent(last_by_type: dict[str, str], artifact_type: str, project_id: str) -> str:
    if artifact_type == "Feature":
        return last_by_type.get("Epic") or project_id
    if artifact_type == "Story":
        return last_by_type.get("Feature") or last_by_type.get("Epic") or project_id
    if artifact_type == "Task":
        return last_by_type.get("Story") or last_by_type.get("Feature") or project_id
    return project_id


def _find_work_item_by_external_id(graph: EngineeringGraph, external_id: Any):
    if external_id is None or external_id == "":
        return None
    suffix = f":{external_id}"
    for node in graph.nodes.values():
        if node.type in WORK_ITEM_TYPES and node.id.endswith(suffix):
            return node
    return None


def _stable_id(node_type: str, name: str) -> str:
    digest = hashlib.sha1(f"{node_type}|{name}".lower().encode("utf-8")).hexdigest()[:16]
    return f"{node_type}:{digest}"


def _canonical_type(value: str) -> str:
    lowered = str(value or "").replace("_", " ").strip().lower()
    if lowered in {"user story", "story"}:
        return "Story"
    return " ".join(part.capitalize() for part in lowered.split()) if lowered else ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _item_name(item: Any, *keys: str) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return _first_text(item, *keys)
    return str(item or "").strip()


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
        if value is not None and not isinstance(value, (dict, list, tuple)):
            return str(value)
    return ""


def _confidence(item: Any) -> float | None:
    if isinstance(item, dict) and item.get("confidence") is not None:
        try:
            return float(item["confidence"])
        except (TypeError, ValueError):
            return None
    return None


def _camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])
