"""Tests for deterministic flow logic extraction."""

import unittest

from backend.repo_context.logic_extractor import (
    build_logic_units_from_flows,
    detect_file_role,
    detect_flow_from_file,
    enrich_graph_with_flows,
    extract_and_update_logic,
    group_files_by_flow,
)
from backend.repo_context.retrieval_bias import (
    collect_session_bias_signals,
    rank_logic_units_with_bias,
    rank_summaries_with_bias,
)


class LogicExtractorTests(unittest.TestCase):
    def test_detect_flow_from_file(self) -> None:
        self.assertEqual(
            detect_flow_from_file("ui/LoginScreen.kt", "Handles login/auth behavior."),
            "login",
        )
        self.assertEqual(
            detect_flow_from_file("billing/PaymentService.py", "handles payment flow."),
            "payment",
        )
        self.assertIsNone(detect_flow_from_file("shared/Formatter.py", "Contains formatting helpers."))

    def test_detect_file_role(self) -> None:
        self.assertEqual(detect_file_role("LoginController.py"), "controller")
        self.assertEqual(detect_file_role("AuthService.py"), "service")
        self.assertEqual(detect_file_role("UserRepository.py"), "data")
        self.assertEqual(detect_file_role("LoginViewModel.kt"), "viewmodel")
        self.assertEqual(detect_file_role("LoginScreen.kt"), "ui")
        self.assertEqual(detect_file_role("AuthApi.ts"), "api")
        self.assertEqual(detect_file_role("helpers.py"), "unknown")

    def test_group_files_by_login_and_payment_flow(self) -> None:
        file_index = [
            {"path": "ui/LoginScreen.kt"},
            {"path": "backend/AuthService.py"},
            {"path": "billing/PaymentService.py"},
        ]
        summaries = [
            {"path": "ui/LoginScreen.kt", "summary": "Handles login/auth behavior."},
            {"path": "backend/AuthService.py", "summary": "Handles login/auth behavior."},
            {"path": "billing/PaymentService.py", "summary": "handles payment flow."},
        ]

        groups = group_files_by_flow(file_index, summaries)

        self.assertEqual(groups["login"]["roles"]["ui"], ["ui/LoginScreen.kt"])
        self.assertEqual(groups["login"]["roles"]["service"], ["backend/AuthService.py"])
        self.assertEqual(groups["payment"]["roles"]["service"], ["billing/PaymentService.py"])
        self.assertEqual(file_index[0]["flow"], "login")
        self.assertEqual(summaries[0]["flow"], "login")
        self.assertEqual(summaries[0]["role"], "ui")

    def test_logic_units_generated_from_roles(self) -> None:
        units = build_logic_units_from_flows(
            {
                "login": {
                    "files": ["ui/LoginScreen.kt", "backend/AuthService.py"],
                    "roles": {"ui": ["ui/LoginScreen.kt"], "service": ["backend/AuthService.py"]},
                }
            }
        )

        self.assertEqual(units[0]["id"], "logic_auth_login")
        self.assertEqual(units[0]["name"], "Login Flow")
        self.assertIn("UI triggers login flow.", units[0]["steps"])
        self.assertIn("Service executes login flow business rules.", units[0]["steps"])
        self.assertIn("session/token", units[0]["outputs"])

    def test_graph_nodes_and_edges_created(self) -> None:
        graph = enrich_graph_with_flows(
            {"nodes": [], "edges": []},
            {
                "login": {
                    "files": ["ui/LoginScreen.kt", "backend/AuthService.py"],
                    "roles": {"ui": ["ui/LoginScreen.kt"], "service": ["backend/AuthService.py"]},
                }
            },
        )

        self.assertIn({"id": "LoginFlow", "type": "flow"}, graph["nodes"])
        self.assertIn({"id": "ui::LoginScreen_kt", "type": "ui"}, graph["nodes"])
        self.assertIn({"from": "ui::LoginScreen_kt", "to": "LoginFlow", "type": "uses"}, graph["edges"])
        self.assertIn({"from": "ui::LoginScreen_kt", "to": "backend::AuthService_py", "type": "invokes"}, graph["edges"])

    def test_incremental_extraction_affects_only_changed_flow(self) -> None:
        file_index = [
            {"path": "ui/LoginScreen.kt"},
            {"path": "billing/PaymentService.py"},
        ]
        summaries = [
            {"path": "ui/LoginScreen.kt", "summary": "Handles login/auth behavior."},
            {"path": "billing/PaymentService.py", "summary": "handles payment flow."},
        ]

        result = extract_and_update_logic(file_index, summaries, [], {"nodes": [], "edges": []}, affected_files=["ui/LoginScreen.kt"])

        self.assertEqual(result["detected_flows"], ["login"])
        self.assertEqual([unit["id"] for unit in result["logic_store"]], ["logic_auth_login"])

    def test_retrieval_bias_prefers_same_flow_logic(self) -> None:
        effective = {
            "file_index": [
                {"path": "ui/LoginScreen.kt", "flow": "login", "module": "ui", "language": "kotlin"},
            ],
            "changed_files": {"added": [], "modified": [], "deleted": []},
        }
        signals = collect_session_bias_signals(effective, "ui/LoginScreen.kt", [])
        ranked = rank_logic_units_with_bias(
            [
                {"id": "logic_auth_login", "flow": "login", "files": []},
                {"id": "logic_payment", "flow": "payment", "files": []},
            ],
            signals,
            query="fix login",
        )

        self.assertEqual(ranked[0][0], "logic_auth_login")
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_retrieval_bias_prefers_same_flow_summaries(self) -> None:
        effective = {
            "file_index": [
                {"path": "ui/LoginScreen.kt", "flow": "login", "module": "ui", "language": "kotlin"},
            ],
            "changed_files": {"added": [], "modified": [], "deleted": []},
        }
        signals = collect_session_bias_signals(effective, "ui/LoginScreen.kt", [])
        ranked = rank_summaries_with_bias(
            [
                {"id": "ui/LoginScreen.kt", "path": "ui/LoginScreen.kt", "flow": "login"},
                {"id": "billing/PaymentService.py", "path": "billing/PaymentService.py", "flow": "payment"},
            ],
            signals,
            query="fix login",
        )

        self.assertEqual(ranked[0][0], "ui/LoginScreen.kt")
        self.assertGreater(ranked[0][1], ranked[1][1])


if __name__ == "__main__":
    unittest.main()
