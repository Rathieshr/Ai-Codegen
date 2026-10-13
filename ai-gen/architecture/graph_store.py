"""Simple JSON-backed architecture graph traversal."""

from __future__ import annotations

import json
from pathlib import Path


def load_graph() -> dict:
    """Load the architecture graph from local JSON."""

    graph_path = Path(__file__).with_name("graph.json")
    with graph_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_node(node_id: str) -> dict | None:
    """Return one graph node by id."""

    graph = load_graph()
    for node in graph.get("nodes", []):
        if node.get("id") == node_id:
            return node
    return None


def get_outgoing(node_id: str) -> list[dict]:
    """Return outgoing edges for one node in graph order."""

    graph = load_graph()
    return [edge for edge in graph.get("edges", []) if edge.get("from") == node_id]


def get_incoming(node_id: str) -> list[dict]:
    """Return incoming edges for one node in graph order."""

    graph = load_graph()
    return [edge for edge in graph.get("edges", []) if edge.get("to") == node_id]


def find_related_nodes(seed_ids: list[str], max_depth: int = 2) -> list[dict]:
    """Find related nodes with deterministic bounded traversal."""

    graph = load_graph()
    nodes_by_id = {node.get("id"): node for node in graph.get("nodes", [])}
    seed_set = set(seed_ids)
    visited = set(seed_ids)
    queue = [(seed_id, 0) for seed_id in seed_ids if seed_id in nodes_by_id]
    related_nodes: list[dict] = []

    while queue:
        node_id, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        for related_id in _neighbor_ids(node_id, graph.get("edges", [])):
            if related_id in visited:
                continue
            visited.add(related_id)

            node = nodes_by_id.get(related_id)
            if not node:
                continue
            if related_id not in seed_set:
                related_nodes.append(node)
            queue.append((related_id, depth + 1))

    return related_nodes


def _neighbor_ids(node_id: str, edges: list[dict]) -> list[str]:
    """Return incoming neighbors first, then outgoing neighbors, without duplicates."""

    neighbors: list[str] = []
    for edge in edges:
        if edge.get("to") == node_id:
            _append_once(neighbors, edge.get("from"))
    for edge in edges:
        if edge.get("from") == node_id:
            _append_once(neighbors, edge.get("to"))
    return neighbors


def _append_once(values: list[str], value: str | None) -> None:
    """Append a non-empty value once."""

    if value and value not in values:
        values.append(value)
