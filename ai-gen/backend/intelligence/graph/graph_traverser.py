from __future__ import annotations

from collections import deque

from .engineering_graph import EngineeringGraph


class GraphTraverser:
    def __init__(self, graph: EngineeringGraph) -> None:
        self.graph = graph

    def traverse(self, start_id: str, depth: int = 2, edge_types: set[str] | None = None) -> list[dict]:
        if start_id not in self.graph.nodes:
            return []
        visited = {start_id}
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])
        result: list[dict] = []
        while queue:
            node_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self.graph.outgoing(node_id):
                if edge_types and edge.type not in edge_types:
                    continue
                if edge.to_node in visited:
                    continue
                visited.add(edge.to_node)
                if edge.to_node in self.graph.nodes:
                    result.append(self.graph.nodes[edge.to_node].to_dict())
                    queue.append((edge.to_node, current_depth + 1))
        return result

    def shortest_path(self, start_id: str, end_id: str, edge_types: set[str] | None = None) -> list[dict]:
        if start_id not in self.graph.nodes or end_id not in self.graph.nodes:
            return []
        queue: deque[tuple[str, list[str]]] = deque([(start_id, [start_id])])
        visited = {start_id}
        while queue:
            node_id, path = queue.popleft()
            if node_id == end_id:
                return [self.graph.nodes[item].to_dict() for item in path]
            for edge in self.graph.outgoing(node_id):
                if edge_types and edge.type not in edge_types:
                    continue
                if edge.to_node not in visited:
                    visited.add(edge.to_node)
                    queue.append((edge.to_node, [*path, edge.to_node]))
        return []
