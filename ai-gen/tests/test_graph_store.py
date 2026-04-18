"""Tests for the MVP architecture graph store."""

import unittest
from unittest.mock import patch

from architecture import graph_store


class GraphStoreTests(unittest.TestCase):
    def test_login_flow_returns_related_components(self) -> None:
        related = graph_store.find_related_nodes(["LoginFlow"], max_depth=2)

        self.assertEqual(
            [node["id"] for node in related],
            ["LoginController", "AuthService", "TokenGeneration"],
        )

    def test_traversal_avoids_duplicates(self) -> None:
        graph = {
            "nodes": [
                {"id": "A", "type": "flow"},
                {"id": "B", "type": "service"},
                {"id": "C", "type": "controller"},
            ],
            "edges": [
                {"from": "A", "to": "B", "type": "uses"},
                {"from": "A", "to": "B", "type": "uses"},
                {"from": "C", "to": "A", "type": "invokes"},
            ],
        }

        with patch("architecture.graph_store.load_graph", return_value=graph):
            related = graph_store.find_related_nodes(["A"], max_depth=2)

        self.assertEqual([node["id"] for node in related], ["C", "B"])

    def test_traversal_handles_cycles_safely(self) -> None:
        graph = {
            "nodes": [
                {"id": "A", "type": "flow"},
                {"id": "B", "type": "service"},
            ],
            "edges": [
                {"from": "A", "to": "B", "type": "uses"},
                {"from": "B", "to": "A", "type": "uses"},
            ],
        }

        with patch("architecture.graph_store.load_graph", return_value=graph):
            related = graph_store.find_related_nodes(["A"], max_depth=2)

        self.assertEqual([node["id"] for node in related], ["B"])

    def test_get_node_and_edges(self) -> None:
        self.assertEqual(graph_store.get_node("LoginFlow")["type"], "flow")
        self.assertEqual(graph_store.get_outgoing("LoginFlow")[0]["to"], "AuthService")
        self.assertEqual(graph_store.get_incoming("LoginFlow")[0]["from"], "LoginController")


if __name__ == "__main__":
    unittest.main()
