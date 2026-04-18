"""Deterministic cross-flow relationship helpers."""

from __future__ import annotations

from typing import Any


FLOW_ALIASES = {
    "auth": "login",
    "authentication": "login",
    "signin": "login",
    "token": "session",
    "jwt": "session",
}


def build_flow_relationships(logic_store: list[dict[str, Any]] | dict[str, Any], graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build an explainable flow relationship map from logic units and graph hints."""

    relationships: dict[str, dict[str, Any]] = {}
    units = _values(logic_store)
    for unit in units:
        source = _flow_for_unit(unit)
        if not source:
            continue
        _ensure_flow(relationships, source)
        for related in _linked_flows_for_unit(unit):
            if related and related != source:
                _add_relationship(relationships, source, related, "depends_on")
        for related in _keyword_related_flows(unit):
            if related != source:
                _add_relationship(relationships, source, related, "affects")

    node_flows = _node_flow_map(graph)
    for edge in graph.get("edges", []):
        from_flows = node_flows.get(str(edge.get("from", "")), [])
        to_flows = node_flows.get(str(edge.get("to", "")), [])
        for source in from_flows:
            for related in to_flows:
                if source != related:
                    _add_relationship(relationships, source, related, str(edge.get("type") or "related"))

    return relationships


def get_related_flows(flow_name: str, relationships: dict[str, dict[str, Any]], max_depth: int = 1) -> list[str]:
    """Return related flows in deterministic breadth-first order."""

    source = normalize_flow_name(flow_name)
    if not source or max_depth < 1:
        return []

    related: list[str] = []
    seen = {source}
    frontier = [source]
    for _ in range(max_depth):
        next_frontier: list[str] = []
        for flow in frontier:
            for candidate in relationships.get(flow, {}).get("related_flows", []):
                normalized = normalize_flow_name(candidate)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                related.append(normalized)
                next_frontier.append(normalized)
        frontier = next_frontier
        if not frontier:
            break
    return related


def normalize_flow_name(value: str) -> str:
    """Normalize ids, names, and graph nodes into compact flow keys."""

    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    if not normalized:
        return ""
    normalized = normalized.replace("flow", "").strip()
    compact = normalized.replace(" ", "")
    if compact.startswith("logic"):
        if "login" in compact or "auth" in compact:
            return "login"
        if "payment" in compact:
            return "payment"
        if "session" in compact:
            return "session"
        if "dashboard" in compact:
            return "dashboard"
        if "profile" in compact:
            return "profile"
    for keyword, alias in FLOW_ALIASES.items():
        if keyword in normalized:
            return alias
    for flow in ("login", "payment", "session", "dashboard", "profile"):
        if flow in normalized:
            return flow
    return compact


def _values(records: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(records, dict):
        return [value for value in records.values() if isinstance(value, dict)]
    return records


def _flow_for_unit(unit: dict[str, Any]) -> str:
    for key in ("flow", "id", "name", "domain"):
        flow = normalize_flow_name(str(unit.get(key, "")))
        if flow:
            return flow
    return ""


def _linked_flows_for_unit(unit: dict[str, Any]) -> list[str]:
    flows: list[str] = []
    for value in unit.get("linked_flows", []):
        if isinstance(value, dict):
            flows.extend([normalize_flow_name(str(value.get("from", ""))), normalize_flow_name(str(value.get("to", "")))])
        else:
            flows.append(normalize_flow_name(str(value)))
    for value in unit.get("depends_on", []):
        flows.append(normalize_flow_name(str(value)))
    return [flow for flow in flows if flow]


def _keyword_related_flows(unit: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(unit.get("id", "")),
            str(unit.get("name", "")),
            str(unit.get("summary", "")),
            " ".join(str(step) for step in unit.get("steps", [])),
            " ".join(str(file_path) for file_path in unit.get("files", [])),
        ]
    ).lower()
    flows: list[str] = []
    if ("login" in text or "auth" in text) and ("session" in text or "token" in text or "jwt" in text):
        flows.extend(["login", "session"])
    if "profile" in text and ("login" in text or "auth" in text):
        flows.extend(["profile", "login"])
    return flows


def _node_flow_map(graph: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for node in graph.get("nodes", []):
        node_id = str(node.get("id", ""))
        if node.get("type") == "flow":
            flow = normalize_flow_name(node_id)
            if flow:
                mapping.setdefault(node_id, [])
                _append_once(mapping[node_id], flow)
    for edge in graph.get("edges", []):
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        for flow in mapping.get(target, []):
            mapping.setdefault(source, [])
            _append_once(mapping[source], flow)
    return mapping


def _ensure_flow(relationships: dict[str, dict[str, Any]], flow: str) -> None:
    relationships.setdefault(flow, {"related_flows": [], "relationship_types": {}})


def _add_relationship(relationships: dict[str, dict[str, Any]], source: str, related: str, relationship_type: str) -> None:
    _ensure_flow(relationships, source)
    _ensure_flow(relationships, related)
    _append_once(relationships[source]["related_flows"], related)
    relationships[source]["relationship_types"][related] = relationship_type


def _append_once(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
