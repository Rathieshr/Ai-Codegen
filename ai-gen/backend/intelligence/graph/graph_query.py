from __future__ import annotations

from .engineering_graph import EngineeringGraph


class GraphQuery:
    def __init__(self, graph: EngineeringGraph) -> None:
        self.graph = graph

    def nodes_by_type(self, node_type: str) -> list[dict]:
        return [node.to_dict() for node in self.graph.nodes_by_type(node_type)]

    def edges_by_type(self, edge_type: str) -> list[dict]:
        return [edge.to_dict() for edge in self.graph.edges_by_type(edge_type)]

    def find_by_name(self, text: str) -> list[dict]:
        needle = text.strip().lower()
        return [node.to_dict() for node in self.graph.nodes.values() if needle in node.name.lower()]

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[dict]:
        return [node.to_dict() for node in self.graph.neighbors(node_id, edge_type)]

    def subgraph_for_node(self, node_id: str, depth: int = 1) -> dict:
        from .graph_traverser import GraphTraverser

        node_ids = {node_id}
        for item in GraphTraverser(self.graph).traverse(node_id, depth=depth):
            node_ids.add(item["id"])
        edge_ids = {
            edge.id
            for edge in self.graph.edges.values()
            if edge.from_node in node_ids and edge.to_node in node_ids
        }
        return {
            "nodes": [self.graph.nodes[item].to_dict() for item in node_ids if item in self.graph.nodes],
            "edges": [self.graph.edges[item].to_dict() for item in edge_ids],
        }
