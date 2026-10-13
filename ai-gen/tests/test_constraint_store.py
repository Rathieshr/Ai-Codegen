"""Tests for deterministic constraint lookup."""

import unittest

from constraints.constraint_store import detect_domains, get_constraints


class ConstraintStoreTests(unittest.TestCase):
    def test_auth_query_returns_auth_constraints(self) -> None:
        constraints = get_constraints("Fix login bug", [], None)

        self.assertIn("Do not remove or bypass credential validation.", constraints)
        self.assertIn("Reuse the existing token/session generation path.", constraints)

    def test_payment_flow_returns_payment_constraints(self) -> None:
        constraints = get_constraints(
            "Update checkout",
            ["Mark payment successful after gateway verification"],
            None,
        )

        self.assertIn(
            "Do not mark payment as successful before gateway verification completes.",
            constraints,
        )
        self.assertIn("Do not skip transaction persistence.", constraints)

    def test_mixed_login_session_flow_returns_both_domains(self) -> None:
        domains = detect_domains(
            "Fix login bug",
            ["Create session token with expiry"],
            ["Login Flow", "SessionLifecycle"],
        )

        self.assertIn("auth", domains)
        self.assertIn("session", domains)

    def test_duplicate_domains_do_not_duplicate_constraints(self) -> None:
        constraints = get_constraints(
            "Fix login token bug",
            ["Validate token", "Refresh session token"],
            ["TokenGeneration"],
        )

        self.assertEqual(
            constraints.count("Reuse the existing token/session generation path."),
            1,
        )

    def test_unrelated_general_query_returns_no_constraints(self) -> None:
        constraints = get_constraints("Explain project structure", [], None)

        self.assertEqual(constraints, [])


if __name__ == "__main__":
    unittest.main()
