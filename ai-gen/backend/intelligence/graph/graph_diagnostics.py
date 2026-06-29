from __future__ import annotations

from collections import Counter

from .engineering_graph import EngineeringGraph


class GraphDiagnostics:
    def __init__(self, graph: EngineeringGraph) -> None:
        self.graph = graph

    def summary(self) -> dict:
        missing = self.missing_endpoint_edges()
        isolated = self.isolated_nodes()
        node_counts = Counter(node.type for node in self.graph.nodes.values())
        edge_counts = Counter(edge.type for edge in self.graph.edges.values())
        total = max(len(self.graph.nodes), 1)
        connected_ratio = (total - len(isolated)) / total
        endpoint_penalty = min(len(missing) * 0.05, 0.5)
        return {
            "schema_version": self.graph.schema_version,
            "node_count": len(self.graph.nodes),
            "edge_count": len(self.graph.edges),
            "node_counts_by_type": dict(sorted(node_counts.items())),
            "edge_counts_by_type": dict(sorted(edge_counts.items())),
            "missing_endpoint_edges": missing,
            "isolated_nodes": isolated,
            "health_score": round(max(0.0, connected_ratio - endpoint_penalty), 2),
        }

    def missing_endpoint_edges(self) -> list[dict]:
        return [
            edge.to_dict()
            for edge in self.graph.edges.values()
            if edge.from_node not in self.graph.nodes or edge.to_node not in self.graph.nodes
        ]

    def isolated_nodes(self) -> list[str]:
        connected: set[str] = set()
        for edge in self.graph.edges.values():
            connected.add(edge.from_node)
            connected.add(edge.to_node)
        return sorted(node_id for node_id in self.graph.nodes if node_id not in connected)
