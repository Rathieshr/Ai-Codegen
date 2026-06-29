from __future__ import annotations

from .engineering_graph import EngineeringGraph


class GraphRanker:
    def __init__(self, graph: EngineeringGraph) -> None:
        self.graph = graph

    def rank_by_degree(self, node_type: str | None = None, limit: int = 10) -> list[dict]:
        nodes = self.graph.nodes.values()
        if node_type:
            nodes = [node for node in nodes if node.type == node_type]
        ranked = []
        for node in nodes:
            degree = len(self.graph.incoming(node.id)) + len(self.graph.outgoing(node.id))
            payload = node.to_dict()
            payload["rank"] = degree
            ranked.append(payload)
        return sorted(ranked, key=lambda item: (-item["rank"], item["name"]))[:limit]

    def rank_references_for(self, node_id: str, edge_types: set[str] | None = None) -> list[dict]:
        refs = []
        for edge in [*self.graph.outgoing(node_id), *self.graph.incoming(node_id)]:
            if edge_types and edge.type not in edge_types:
                continue
            other_id = edge.to_node if edge.from_node == node_id else edge.from_node
            node = self.graph.get_node(other_id)
            if not node:
                continue
            payload = node.to_dict()
            payload["edgeType"] = edge.type
            payload["confidence"] = edge.confidence if edge.confidence is not None else payload.get("confidence", 0.0)
            refs.append(payload)
        return sorted(refs, key=lambda item: (-float(item.get("confidence") or 0), item["name"]))
