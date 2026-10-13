"""Semantic projections from repository snapshots and execution results."""

from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

from backend.token_intelligence.models import stable_hash


CATEGORIES = (
    "apis",
    "modules",
    "services",
    "dependencies",
    "architecture",
    "tests",
    "security",
    "configuration",
    "database",
    "documentation",
)


def project_snapshot(snapshot: dict[str, Any], label: str) -> dict[str, Any]:
    metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
    result = {category: [] for category in CATEGORIES}
    result["modules"].extend(_records(snapshot.get("modules") or metadata.get("modules"), "Module", label))
    result["apis"].extend(_records(_first(snapshot, metadata, "apis", "routes"), "API", label))
    result["services"].extend(_records(_first(snapshot, metadata, "services"), "Service", label))
    result["dependencies"].extend(_records(_first(snapshot, metadata, "dependencies"), "Dependency", label))
    result["architecture"].extend(_records(_first(snapshot, metadata, "architecture", "architectureNotes"), "Architecture", label))
    result["security"].extend(_records(_first(snapshot, metadata, "security", "securityRules"), "Security", label))

    symbols = _items(snapshot.get("symbols") or metadata.get("symbols"))
    for symbol in symbols:
        kind = _text(symbol, "kind", "symbolKind", "type").casefold()
        if kind in {"route", "api", "controller"}:
            result["apis"].append(_record(symbol, "API", label))
        if kind == "service" or _text(symbol, "name").casefold().endswith("service"):
            result["services"].append(_record(symbol, "Service", label))
        if kind == "test":
            result["tests"].append(_record(symbol, "Test", label))

    graph = snapshot.get("engineeringGraph") or snapshot.get("graph") or metadata.get("engineeringGraph") or metadata.get("graph") or {}
    for node in _items(graph.get("nodes") if isinstance(graph, dict) else []):
        node_type = _text(node, "nodeType", "type", "kind").casefold()
        mapping = {"api": ("apis", "API"), "controller": ("apis", "API"), "service": ("services", "Service"), "module": ("modules", "Module"), "test": ("tests", "Test")}
        if node_type in mapping:
            category, kind = mapping[node_type]
            result[category].append(_record(node, kind, label))

    files = _items(metadata.get("files") or snapshot.get("files"))
    for file_item in files:
        path = _text(file_item, "path", "file")
        lower = path.casefold()
        if not path:
            continue
        if "test" in lower or "spec" in PurePosixPath(lower).name:
            result["tests"].append(_record(file_item, "Test", label))
        if lower.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".config", ".xml")):
            result["configuration"].append(_record(file_item, "Configuration", label))
        if lower.endswith(".sql") or "migration" in lower:
            result["database"].append(_record(file_item, "Database", label))
        if lower.endswith((".md", ".rst", ".txt")) or lower.startswith("docs/"):
            result["documentation"].append(_record(file_item, "Documentation", label))

    for category in CATEGORIES:
        result[category] = _dedupe(result[category])
    result["graph"] = _graph_projection(graph, label)
    result["renamed"] = deepcopy((metadata.get("diff") or {}).get("renamed") or []) if isinstance(metadata.get("diff"), dict) else []
    return result


def project_execution_result(execution_result: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {category: [] for category in (*CATEGORIES, "refactorings", "breakingChanges")}
    artifacts = execution_result.get("engineeringArtifacts") or execution_result.get("artifacts") or []
    for artifact in _items(artifacts):
        artifact_type = _text(artifact, "type", "artifactType").casefold()
        title = _text(artifact, "title", "name", "path")
        content = _text(artifact, "content", "description")
        combined = f"{title} {content}".casefold()
        category = ""
        kind = _text(artifact, "type") or "Unknown"
        if artifact_type in {"api"}:
            category = "apis"
        elif artifact_type in {"test"}:
            category = "tests"
        elif artifact_type in {"configuration", "configurationchange"}:
            category = "configuration"
        elif artifact_type in {"migration", "databasechange"}:
            category = "database"
        elif artifact_type in {"documentation", "documentationchange"}:
            category = "documentation"
        elif artifact_type in {"architecture", "architecturenote"}:
            category = "architecture"
        elif artifact_type == "refactoring":
            category = "refactorings"
        elif artifact_type == "breakingchange":
            category = "breakingChanges"
        elif "service" in title.casefold() and artifact_type in {"code", "class", "interface", "method"}:
            category = "services"
        elif any(token in combined for token in ("authorization", "authentication", "security", "permission", "credential")) and artifact_type in {"security", "warning", "risk", "implementationnote"}:
            category = "security"
        if category:
            record = _record(artifact, kind, "ExecutionResult")
            record["changeType"] = _change_type(artifact.get("changeType"))
            result[category].append(record)

    structured = execution_result.get("structuredExecutionResult") or execution_result.get("structuredResponse") or {}
    if isinstance(structured, dict):
        for value in _items(structured.get("dependencies")):
            record = _record(value, "Dependency", "ExecutionResult")
            record["changeType"] = _change_type(value.get("changeType") if isinstance(value, dict) else "Modified")
            result["dependencies"].append(record)
        for value in _items(structured.get("breakingChanges") or structured.get("breaking_changes")):
            record = _record(value, "BreakingChange", "ExecutionResult")
            record["changeType"] = "Modified"
            result["breakingChanges"].append(record)
    return {key: _dedupe(value) for key, value in result.items()}


def _records(values: Any, kind: str, source: str) -> list[dict[str, Any]]:
    return [_record(item, kind, source) for item in _items(values) if _name(item)]


def _record(value: Any, kind: str, source: str) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {"name": str(value)}
    name = _name(item)
    path = _text(item, "path", "file", "filePath")
    method = _text(item, "method", "httpMethod")
    route = _text(item, "route", "url", "endpoint")
    identity = f"{method.upper()} {route}".strip() if route else name
    identity = identity or path
    signature = _text(item, "signature", "contentHash", "hash", "version", "schema")
    if not signature:
        signature = stable_hash({key: value for key, value in item.items() if key not in {"snapshotId", "snapshotVersion", "createdAt", "lastModified", "confidence", "evidence"}})
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    evidence = [str(entry) for entry in evidence if str(entry)] or [f"{source} identifies {kind}: {identity or path}."]
    return {
        "key": identity.casefold(),
        "name": identity,
        "path": path,
        "kind": kind,
        "signature": signature,
        "module": _text(item, "module", "namespace", "container") or _module(path),
        "source": source,
        "evidence": evidence,
        "reason": f"Compared as a semantic {kind.lower()} from {source}.",
        "confidence": _confidence(item.get("confidence"), 0.92 if source != "ExecutionResult" else 0.84),
        "raw": deepcopy(item),
    }


def _graph_projection(graph: Any, source: str) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(graph, dict):
        return {"nodes": [], "edges": []}
    nodes = [_record(value, _text(value, "nodeType", "type") or "Node", source) for value in _items(graph.get("nodes"))]
    edges: list[dict[str, Any]] = []
    for value in _items(graph.get("relationships") or graph.get("edges")):
        item = value if isinstance(value, dict) else {}
        from_id = _text(item, "fromNodeId", "from", "source")
        to_id = _text(item, "toNodeId", "to", "target")
        relationship = _text(item, "relationshipType", "type", "relationship")
        key = f"{from_id}|{relationship}|{to_id}".casefold()
        if from_id or to_id:
            edges.append({"key": key, "from": from_id, "to": to_id, "type": relationship, "source": source, "evidence": [f"{source} graph relationship: {from_id} {relationship} {to_id}."], "confidence": _confidence(item.get("confidence"), 0.9), "raw": deepcopy(item)})
    return {"nodes": _dedupe(nodes), "edges": _dedupe(edges)}


def _dedupe(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = str(value.get("key") or "")
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _first(snapshot: dict[str, Any], metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if snapshot.get(key) is not None:
            return snapshot.get(key)
        if metadata.get(key) is not None:
            return metadata.get(key)
    return []


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return str(value or "").strip()
    return _text(value, "name", "title", "route", "path", "id", "nodeId")


def _text(value: Any, *keys: str) -> str:
    if not isinstance(value, dict):
        return str(value or "").strip()
    for key in keys:
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def _module(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else ""


def _change_type(value: Any) -> str:
    normalized = str(value or "Modified").strip().casefold()
    return {"add": "Added", "added": "Added", "create": "Added", "delete": "Removed", "deleted": "Removed", "remove": "Removed", "removed": "Removed", "move": "Moved", "moved": "Moved", "rename": "Moved", "renamed": "Moved"}.get(normalized, "Modified")


def _confidence(value: Any, fallback: float) -> float:
    try:
        return round(max(0.05, min(1.0, float(value))), 2) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback
