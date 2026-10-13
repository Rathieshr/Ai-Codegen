"""Tests for deterministic cross-flow reasoning."""

import unittest

from backend.repo_context.cross_flow import build_flow_relationships, get_related_flows


class CrossFlowTests(unittest.TestCase):
    def test_login_relates_to_session_from_linked_flows(self) -> None:
        relationships = build_flow_relationships(
            [
                {
                    "id": "logic_auth_login",
                    "name": "Login Flow",
                    "linked_flows": [{"from": "Login Flow", "to": "Session Flow"}],
                }
            ],
            {"nodes": [], "edges": []},
        )

        self.assertEqual(relationships["login"]["related_flows"], ["session"])
        self.assertEqual(relationships["login"]["relationship_types"]["session"], "depends_on")

    def test_related_flows_resolved_deterministically(self) -> None:
        relationships = {
            "login": {"related_flows": ["session", "profile"], "relationship_types": {}},
            "session": {"related_flows": ["payment"], "relationship_types": {}},
        }

        self.assertEqual(get_related_flows("Login Flow", relationships), ["session", "profile"])
        self.assertEqual(get_related_flows("Login Flow", relationships, max_depth=2), ["session", "profile", "payment"])

    def test_graph_edges_between_flow_nodes_create_relationship(self) -> None:
        relationships = build_flow_relationships(
            [],
            {
                "nodes": [
                    {"id": "LoginFlow", "type": "flow"},
                    {"id": "SessionFlow", "type": "flow"},
                ],
                "edges": [
                    {"from": "LoginFlow", "to": "SessionFlow", "type": "depends_on"},
                ],
            },
        )

        self.assertEqual(get_related_flows("login", relationships), ["session"])

    def test_login_session_keyword_coupling_adds_relationship(self) -> None:
        relationships = build_flow_relationships(
            [
                {
                    "id": "logic_auth_login",
                    "name": "Login Flow",
                    "steps": ["Validate credentials", "Session/token is created after validation"],
                }
            ],
            {"nodes": [], "edges": []},
        )

        self.assertEqual(get_related_flows("login", relationships), ["session"])


if __name__ == "__main__":
    unittest.main()
