"""Deterministic dependency management for Planning Workspace artifacts."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Callable
from uuid import uuid4


DEPENDENCY_TYPES = ("Depends On", "Blocked By")
PLANNING_ARTIFACT_TYPES = {"requirement", "epic", "feature", "story", "task"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    values: list[str] = []
    for item in _list(value):
        text = _text(item.get("name") or item.get("title") or item.get("reference")) if isinstance(item, dict) else _text(item)
        if text and text not in values:
            values.append(text)
    return values


class PlanningDependencyService:
    """Stores links on planning artifacts and projects execution order views."""

    def __init__(self, *, planning_service: Any, artifact_provider: Callable[[], dict[str, Any]]) -> None:
        self.planning = planning_service
        self.artifact_provider = artifact_provider

    def get(self, planning_id: str, project_id: str = "") -> dict[str, Any]:
        hierarchy = self.planning.hierarchy(planning_id, project_id)
        nodes = [dict(item) for item in _list(hierarchy.get("nodes")) if isinstance(item, dict)]
        by_id = {item["id"]: item for item in nodes}
        aliases: dict[str, list[dict[str, Any]]] = {}
        for item in nodes:
            # sourceItemId often identifies the parent work item, so using it as a
            # target alias makes one parent ID resolve to both parent and child.
            for alias in (item.get("id"), item.get("title")):
                if _text(alias):
                    aliases.setdefault(_text(alias).casefold(), []).append(item)

        raw_artifacts = self._artifacts()
        raw_by_id = {_text(item.get("artifact_id")): item for item in raw_artifacts}
        links: list[dict[str, Any]] = []
        explicit_keys: set[tuple[str, str]] = set()
        for source in nodes:
            artifact = raw_by_id.get(source["id"])
            payload = _dict((artifact or {}).get("payload")) or _dict(source.get("details"))
            for raw_link in _list(payload.get("dependencyLinks")):
                if not isinstance(raw_link, dict):
                    continue
                link = self._resolve_link(raw_link, source, aliases, raw_by_id)
                links.append(link)
                explicit_keys.add((source["id"], _text(link.get("targetReference")).casefold()))
                if link.get("targetId"):
                    explicit_keys.add((source["id"], _text(link.get("targetId")).casefold()))

            for reference in _strings(payload.get("dependencies")):
                matches = aliases.get(reference.casefold(), [])
                target = matches[0] if len(matches) == 1 else None
                key = (source["id"], _text((target or {}).get("id") or reference).casefold())
                if key in explicit_keys or (source["id"], reference.casefold()) in explicit_keys:
                    continue
                legacy = {
                    "dependencyId": f"dep_legacy_{sha256(f'{source['id']}:{reference}'.encode()).hexdigest()[:12]}",
                    "sourceId": source["id"], "sourceTitle": source["title"],
                    "targetId": _text((target or {}).get("id")), "targetTitle": _text((target or {}).get("title")) or reference,
                    "targetReference": reference, "dependencyType": "Depends On", "source": "legacy",
                    "editable": False,
                }
                links.append(self._resolve_link(legacy, source, aliases, raw_by_id))

        cycle_ids, cycle_nodes = _find_cycles(links)
        for link in links:
            if link["dependencyId"] in cycle_ids:
                link["status"] = "Circular"
                link["warning"] = "This dependency participates in a circular execution order."

        critical = _critical_path(nodes, links, cycle_ids)
        critical_ids = set(critical["dependencyIds"])
        for link in links:
            link["criticalPath"] = link["dependencyId"] in critical_ids

        warnings = _warnings(links, cycle_nodes)
        depended_on = {link.get("targetId") for link in links if link.get("targetId") and link.get("status") == "Active"}
        node_view = [{
            "id": item["id"], "type": item["type"], "title": item["title"], "status": item["status"],
            "editable": item.get("source") == "planning_artifact" and item.get("status") in {"Draft", "Review"},
            "dependencyCount": sum(1 for link in links if link["sourceId"] == item["id"]),
            "dependentCount": sum(1 for link in links if link.get("targetId") == item["id"]),
            "onCriticalPath": item["id"] in critical["nodeIds"], "blocksOtherWork": item["id"] in depended_on,
        } for item in nodes]
        return {
            "schemaVersion": "hei-planning-dependencies-v1", "planningId": planning_id,
            "summary": {
                "dependencies": len(links), "active": sum(1 for link in links if link["status"] == "Active"),
                "circular": sum(1 for link in links if link["status"] == "Circular"),
                "missing": sum(1 for link in links if link["status"] == "Missing"),
                "broken": sum(1 for link in links if link["status"] == "Broken"),
            },
            "nodes": node_view, "dependencies": links,
            "tree": _tree_view(node_view, links),
            "graph": {"nodes": node_view, "edges": links},
            "table": links,
            "criticalPath": critical, "warnings": warnings,
            "dependencyTypes": list(DEPENDENCY_TYPES),
        }

    def put(self, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        dependency_id = _text(request.get("dependencyId"))
        existing = self._find_link(dependency_id) if dependency_id else None
        existing_source_id = _text(_dict(existing).get("sourceId"))
        requested_source_id = _text(request.get("sourceId"))
        if existing_source_id and requested_source_id and existing_source_id != requested_source_id:
            raise ValueError("An existing dependency cannot be moved to another source artifact.")
        source_id = existing_source_id or requested_source_id
        if not source_id:
            raise ValueError("sourceId is required.")
        source = self._artifact(source_id)
        if _text(source.get("state")).casefold() not in {"draft", "review"}:
            raise ValueError("Dependencies can only be changed on Draft or Review planning artifacts.")
        target_id = _text(request.get("targetId") or _dict(existing).get("targetId"))
        target_reference = _text(request.get("targetReference") or _dict(existing).get("targetReference"))
        if not target_id and not target_reference:
            raise ValueError("targetId or targetReference is required.")
        if target_id == source_id:
            raise ValueError("A planning artifact cannot depend on itself.")
        target = self._artifact(target_id, required=False) if target_id else None
        if target_id and not target:
            target_reference = target_reference or target_id
        dependency_type = _normalize_type(request.get("dependencyType") or _dict(existing).get("dependencyType"))
        payload = _dict(source.get("payload"))
        links = [dict(item) for item in _list(payload.get("dependencyLinks")) if isinstance(item, dict)]
        new_link = {
            "dependencyId": dependency_id or f"dep_{uuid4().hex[:16]}", "sourceId": source_id,
            "targetId": target_id, "targetReference": target_reference or _text((target or {}).get("title")),
            "dependencyType": dependency_type, "reason": _text(request.get("reason") or _dict(existing).get("reason")),
            "source": "manual",
        }
        replaced = False
        for index, link in enumerate(links):
            if _text(link.get("dependencyId")) == new_link["dependencyId"]:
                links[index] = new_link; replaced = True; break
        if not replaced:
            duplicate = next((link for link in links if _text(link.get("targetId")) == target_id and _normalize_type(link.get("dependencyType")) == dependency_type), None)
            if duplicate and target_id:
                raise ValueError("This dependency already exists.")
            links.append(new_link)
        self._save_links(source, links, actor, request.get("expectedVersion"))
        planning_id = _text(request.get("planningId")) or _root_id(source_id, self.planning.list(limit=250).get("items", []))
        return {"dependencyId": new_link["dependencyId"], "created": not replaced, "dependencies": self.get(planning_id)}

    def delete(self, dependency_id: str, actor: str = "") -> dict[str, Any]:
        found = self._find_link(dependency_id)
        if not found:
            raise LookupError(f"Dependency {dependency_id} was not found.")
        source = self._artifact(_text(found.get("sourceId")))
        if _text(source.get("state")).casefold() not in {"draft", "review"}:
            raise ValueError("Dependencies can only be deleted from Draft or Review planning artifacts.")
        payload = _dict(source.get("payload"))
        links = [dict(item) for item in _list(payload.get("dependencyLinks")) if isinstance(item, dict) and _text(item.get("dependencyId")) != dependency_id]
        self._save_links(source, links, actor, None, removed_reference=_text(found.get("targetReference")))
        return {"deleted": True, "dependencyId": dependency_id, "sourceId": found.get("sourceId")}

    def _resolve_link(self, raw: dict[str, Any], source: dict[str, Any], aliases: dict[str, list[dict[str, Any]]], raw_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
        target_id = _text(raw.get("targetId"))
        reference = _text(raw.get("targetReference") or raw.get("targetTitle") or target_id)
        matches = aliases.get(target_id.casefold(), []) if target_id else []
        if not matches and reference:
            matches = aliases.get(reference.casefold(), [])
        target = matches[0] if len(matches) == 1 else None
        archived = raw_by_id.get(target_id)
        status = "Active"
        warning = ""
        if archived and _text(archived.get("state")).casefold() == "archived":
            status, warning = "Broken", "The target artifact is archived or rejected."
        elif not target:
            status = "Missing"
            warning = "Multiple matching targets were found." if len(matches) > 1 else "The dependency target could not be resolved."
        return {
            "dependencyId": _text(raw.get("dependencyId")) or f"dep_{uuid4().hex[:16]}",
            "sourceId": source["id"], "sourceTitle": source["title"], "sourceType": source["type"],
            "targetId": _text((target or {}).get("id") or target_id),
            "targetTitle": _text((target or {}).get("title")) or reference,
            "targetType": _text((target or {}).get("type")) or "Unknown", "targetReference": reference,
            "dependencyType": _normalize_type(raw.get("dependencyType")), "reason": _text(raw.get("reason")),
            "status": status, "warning": warning, "criticalPath": False,
            "source": _text(raw.get("source")) or "manual", "editable": raw.get("editable", True),
        }

    def _save_links(self, source: dict[str, Any], links: list[dict[str, Any]], actor: str, expected_version: Any, removed_reference: str = "") -> None:
        payload = _dict(source.get("payload"))
        names = _strings(payload.get("dependencies"))
        if removed_reference:
            names = [name for name in names if name.casefold() != removed_reference.casefold()]
        names = _unique([*names, *[_text(link.get("targetReference") or link.get("targetId")) for link in links]])
        self.planning.artifact_updater(_text(source.get("artifact_id")), {
            "expectedVersion": expected_version if expected_version is not None else source.get("version"),
            "details": {"dependencyLinks": links, "dependencies": names},
        }, actor)

    def _find_link(self, dependency_id: str) -> dict[str, Any] | None:
        for artifact in self._artifacts():
            for link in _list(_dict(artifact.get("payload")).get("dependencyLinks")):
                if isinstance(link, dict) and _text(link.get("dependencyId")) == dependency_id:
                    return {**link, "sourceId": _text(artifact.get("artifact_id"))}
        return None

    def _artifact(self, artifact_id: str, *, required: bool = True) -> dict[str, Any] | None:
        artifact = next((item for item in self._artifacts() if _text(item.get("artifact_id")) == artifact_id), None)
        if required and not artifact:
            raise LookupError(f"Planning artifact {artifact_id} was not found.")
        if artifact and _text(artifact.get("artifact_type")).casefold() not in PLANNING_ARTIFACT_TYPES:
            raise ValueError(f"Artifact {artifact_id} is not a planning artifact.")
        return artifact

    def _artifacts(self) -> list[dict[str, Any]]:
        return [item for item in _list(self.artifact_provider().get("artifacts")) if isinstance(item, dict)]


def _normalize_type(value: Any) -> str:
    text = _text(value).replace("_", " ").casefold()
    normalized = "Blocked By" if text in {"blocked by", "blockedby", "blocker"} else "Depends On"
    if text and normalized.casefold() != text:
        if text not in {"depends on", "dependson", "dependency", "blocked by", "blockedby", "blocker"}:
            raise ValueError(f"Unsupported dependency type: {_text(value)}.")
    return normalized


def _find_cycles(links: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for link in links:
        if link.get("status") == "Active" and link.get("targetId"):
            adjacency.setdefault(link["sourceId"], []).append((link["targetId"], link["dependencyId"]))
    cycle_edges: set[str] = set()
    cycle_nodes: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    stack_edges: list[str] = []

    def visit(node: str) -> None:
        if node in stack:
            index = stack.index(node)
            cycle_nodes.update(stack[index:])
            cycle_edges.update(stack_edges[index:])
            return
        if node in visited:
            return
        stack.append(node)
        for target, edge_id in adjacency.get(node, []):
            stack_edges.append(edge_id); visit(target); stack_edges.pop()
        stack.pop(); visited.add(node)

    for node in list(adjacency):
        visit(node)
    return cycle_edges, cycle_nodes


def _critical_path(nodes: list[dict[str, Any]], links: list[dict[str, Any]], cycle_ids: set[str]) -> dict[str, Any]:
    node_ids = {item["id"] for item in nodes}
    outgoing: dict[str, list[tuple[str, str]]] = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}
    valid_edges = 0
    for link in links:
        if link.get("status") != "Active" or link["dependencyId"] in cycle_ids or link.get("targetId") not in node_ids:
            continue
        prerequisite, dependent = link["targetId"], link["sourceId"]
        outgoing[prerequisite].append((dependent, link["dependencyId"])); indegree[dependent] += 1; valid_edges += 1
    if not valid_edges:
        return {"nodeIds": [], "dependencyIds": [], "titles": [], "totalWeight": 0, "unit": "planning points"}
    queue = sorted([node for node, degree in indegree.items() if degree == 0])
    distance = {node: _node_weight(next(item for item in nodes if item["id"] == node)) for node in node_ids}
    previous: dict[str, tuple[str, str]] = {}
    while queue:
        current = queue.pop(0)
        for dependent, edge_id in outgoing[current]:
            weight = _node_weight(next(item for item in nodes if item["id"] == dependent))
            if distance[current] + weight > distance[dependent]:
                distance[dependent] = distance[current] + weight; previous[dependent] = (current, edge_id)
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent); queue.sort()
    if not distance:
        return {"nodeIds": [], "dependencyIds": [], "titles": [], "totalWeight": 0, "unit": "planning points"}
    end = max(distance, key=lambda node: (distance[node], node))
    path_nodes = [end]; path_edges: list[str] = []
    while end in previous:
        end, edge_id = previous[end]; path_nodes.append(end); path_edges.append(edge_id)
    path_nodes.reverse(); path_edges.reverse()
    titles = {item["id"]: item["title"] for item in nodes}
    return {"nodeIds": path_nodes, "dependencyIds": path_edges, "titles": [titles[node] for node in path_nodes], "totalWeight": round(distance[path_nodes[-1]], 2), "unit": "planning points"}


def _node_weight(node: dict[str, Any]) -> float:
    details = _dict(node.get("details")); estimate = _dict(details.get("estimate") or details.get("engineeringEstimate"))
    candidates = (
        (estimate.get("engineeringDays"), 1.0),
        (node.get("storyPoints"), 1.0),
        (estimate.get("engineeringHours"), 1 / 8),
    )
    for value, multiplier in candidates:
        try:
            number = float(value or 0)
            if number > 0:
                return number * multiplier
        except (TypeError, ValueError):
            continue
    return 1.0


def _tree_view(nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**node, "dependsOn": [link for link in links if link["sourceId"] == node["id"]]} for node in nodes if any(link["sourceId"] == node["id"] for link in links)]


def _warnings(links: list[dict[str, Any]], cycle_nodes: set[str]) -> list[dict[str, Any]]:
    result = []
    if cycle_nodes:
        result.append({"type": "Circular Dependency", "severity": "Blocking", "message": "Circular execution order detected.", "nodeIds": sorted(cycle_nodes)})
    for status, warning_type in (("Missing", "Missing Dependency"), ("Broken", "Broken Dependency")):
        for link in links:
            if link["status"] == status:
                result.append({"type": warning_type, "severity": "Warning" if status == "Missing" else "Blocking", "message": link["warning"], "dependencyId": link["dependencyId"], "sourceId": link["sourceId"], "targetReference": link["targetReference"]})
    return result


def _root_id(item_id: str, items: list[dict[str, Any]]) -> str:
    by_id = {_text(item.get("id")): item for item in items if isinstance(item, dict)}
    current = item_id; visited = {current}
    while current in by_id and _text(by_id[current].get("parentId")) and _text(by_id[current].get("parentId")) not in visited:
        current = _text(by_id[current].get("parentId")); visited.add(current)
    return current


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
