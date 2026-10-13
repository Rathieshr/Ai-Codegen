from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .graph_edge import GraphEdge
from .graph_node import GraphNode


GRAPH_SCHEMA_VERSION = "engineering-graph-v1"


@dataclass
class EngineeringGraph:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: dict[str, GraphEdge] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = GRAPH_SCHEMA_VERSION

    def add_node(self, node: GraphNode | dict[str, Any]) -> GraphNode:
        graph_node = node if isinstance(node, GraphNode) else GraphNode.from_dict(node)
        if graph_node.id in self.nodes:
            graph_node = self.nodes[graph_node.id].merge(graph_node)
        self.nodes[graph_node.id] = graph_node
        return graph_node

    def add_edge(self, edge: GraphEdge | dict[str, Any], *, require_nodes: bool = True) -> GraphEdge:
        graph_edge = edge if isinstance(edge, GraphEdge) else GraphEdge.from_dict(edge)
        if require_nodes and (graph_edge.from_node not in self.nodes or graph_edge.to_node not in self.nodes):
            raise ValueError(f"GraphEdge endpoint is missing: {graph_edge.from_node} -> {graph_edge.to_node}")
        self.edges[graph_edge.id] = graph_edge
        return graph_edge

    def add_nodes(self, nodes: Iterable[GraphNode | dict[str, Any]]) -> None:
        for node in nodes:
            self.add_node(node)

    def add_edges(self, edges: Iterable[GraphEdge | dict[str, Any]], *, require_nodes: bool = True) -> None:
        for edge in edges:
            self.add_edge(edge, require_nodes=require_nodes)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(str(node_id))

    def outgoing(self, node_id: str, edge_type: str | None = None) -> list[GraphEdge]:
        return [
            edge
            for edge in self.edges.values()
            if edge.from_node == node_id and (edge_type is None or edge.type == edge_type)
        ]

    def incoming(self, node_id: str, edge_type: str | None = None) -> list[GraphEdge]:
        return [
            edge
            for edge in self.edges.values()
            if edge.to_node == node_id and (edge_type is None or edge.type == edge_type)
        ]

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[GraphNode]:
        neighbor_ids = [edge.to_node for edge in self.outgoing(node_id, edge_type)]
        return [self.nodes[item] for item in neighbor_ids if item in self.nodes]

    def nodes_by_type(self, node_type: str) -> list[GraphNode]:
        return [node for node in self.nodes.values() if node.type == node_type]

    def edges_by_type(self, edge_type: str) -> list[GraphEdge]:
        return [edge for edge in self.edges.values() if edge.type == edge_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metadata": dict(self.metadata),
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges.values()],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EngineeringGraph":
        graph = cls(
            metadata=dict(payload.get("metadata") or {}),
            schema_version=str(payload.get("schema_version") or GRAPH_SCHEMA_VERSION),
        )
        graph.add_nodes(GraphNode.from_dict(node) for node in payload.get("nodes", []))
        graph.add_edges((GraphEdge.from_dict(edge) for edge in payload.get("edges", [])), require_nodes=False)
        return graph
