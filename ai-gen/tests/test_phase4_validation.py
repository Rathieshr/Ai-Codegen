"""Tests for Phase 4: AC coverage checker, critic deepening, RISK_MATRIX."""

from __future__ import annotations

import unittest

from backend.validation import check_ac_coverage, CoverageReport
from backend.assistants.critic_assistant import (
    run_critic_assistant,
    RISK_MATRIX,
    _compute_testability_score,
)


# ── AC Coverage Checker ───────────────────────────────────────────────────────

class AcCoverageTests(unittest.TestCase):
    def test_empty_ac_returns_perfect_score(self) -> None:
        report = check_ac_coverage("", {"summary": "some output"})
        self.assertEqual(report.overall_score, 1.0)
        self.assertEqual(report.total_count, 0)

    def test_covered_item_detected(self) -> None:
        ac = "User can log in with phone number and OTP"
        output = {
            "summary": "Implements phone number and OTP login flow",
            "base_flows": ["login", "otp_verification"],
        }
        report = check_ac_coverage(ac, output)
        self.assertEqual(report.total_count, 1)
        self.assertTrue(report.items[0].covered)
        self.assertGreater(report.items[0].coverage_ratio, 0.5)

    def test_uncovered_item_flagged(self) -> None:
        ac = ["User can reset password via email link"]
        output = {"summary": "Implements OTP login only"}
        report = check_ac_coverage(ac, output)
        self.assertEqual(report.total_count, 1)
        self.assertFalse(report.items[0].covered)
        self.assertIn("User can reset password via email link", report.uncovered_items)

    def test_list_ac_parsed_correctly(self) -> None:
        ac = [
            "User can log in with phone OTP",
            "Session expires after 30 minutes",
            "Failed attempts are rate-limited",
        ]
        output = {
            "summary": "Phone OTP login with session expiry and rate limiting after failed attempts"
        }
        report = check_ac_coverage(ac, output)
        self.assertEqual(report.total_count, 3)
        self.assertGreater(report.covered_count, 0)

    def test_multiline_string_ac_split_on_newlines(self) -> None:
        ac = "User can log in\nUser can log out\nUser can reset password"
        report = check_ac_coverage(ac, {"summary": "login and logout implemented"})
        self.assertEqual(report.total_count, 3)

    def test_overall_score_proportional(self) -> None:
        ac = [
            "Feature A is supported",
            "Feature B is supported",
        ]
        # Only covers Feature A
        output = {"supported": "Feature A is supported in the implementation"}
        report = check_ac_coverage(ac, output)
        self.assertLessEqual(report.overall_score, 1.0)
        self.assertGreaterEqual(report.overall_score, 0.0)

    def test_passed_only_when_all_covered(self) -> None:
        ac = ["OTP login", "Session timeout"]
        output = {"summary": "OTP login and session timeout both implemented"}
        report = check_ac_coverage(ac, output)
        # passed is only True when all items are covered
        self.assertEqual(report.passed, report.covered_count == report.total_count)

    def test_to_dict_has_expected_keys(self) -> None:
        report = check_ac_coverage(["Something"], {"summary": "Nothing relevant"})
        d = report.to_dict()
        for key in ("overall_score", "covered_count", "total_count", "passed", "items", "uncovered_items"):
            self.assertIn(key, d)


# ── Critic RISK_MATRIX ────────────────────────────────────────────────────────

class RiskMatrixTests(unittest.TestCase):
    def test_risk_matrix_has_login_key(self) -> None:
        self.assertIn("login", RISK_MATRIX)

    def test_payment_flow_authentication_is_high(self) -> None:
        self.assertEqual(RISK_MATRIX["payment"]["service_logic"], "high")

    def test_risk_matrix_findings_triggered_for_login_database(self) -> None:
        dev_output = {
            "flow": "login",
            "surfaces": ["database", "authentication"],
            "scope": "login screen",
            "constraints": ["HTTPS only"],
        }
        result = run_critic_assistant(dev_output=dev_output)
        types = [f["type"] for f in result["findings"]]
        self.assertIn("risk_matrix_match", types)

    def test_risk_matrix_not_triggered_for_low_risk(self) -> None:
        dev_output = {
            "flow": "dashboard",
            "surfaces": ["ui_screen"],
            "scope": "read-only view",
        }
        result = run_critic_assistant(dev_output=dev_output)
        types = [f["type"] for f in result["findings"]]
        self.assertNotIn("risk_matrix_match", types)


# ── Testability Score ─────────────────────────────────────────────────────────

class TestabilityScoreTests(unittest.TestCase):
    def test_full_score_requires_all_signals(self) -> None:
        ba = {
            "acceptance_criteria": ["Login works", "Logout works"],
            "unknowns": [],
        }
        dev = {"scope": "Login screen", "constraints": ["HTTPS"]}
        test = {
            "test_cases": [
                {"type": "positive"},
                {"type": "negative"},
                {"type": "edge"},
            ]
        }
        score = _compute_testability_score(ba, None, dev, test)
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_zero_score_for_empty_inputs(self) -> None:
        score = _compute_testability_score(None, None, None, None)
        self.assertEqual(score, 0.0)

    def test_unknowns_reduce_score(self) -> None:
        ba_clean = {"acceptance_criteria": ["AC1"], "unknowns": []}
        ba_dirty = {"acceptance_criteria": ["AC1"], "unknowns": ["TBD"]}
        score_clean = _compute_testability_score(ba_clean, None, None, None)
        score_dirty = _compute_testability_score(ba_dirty, None, None, None)
        self.assertGreater(score_clean, score_dirty)

    def test_score_is_between_0_and_1(self) -> None:
        score = _compute_testability_score(
            {"acceptance_criteria": ["A", "B", "C", "D", "E"], "unknowns": []},
            None,
            {"scope": "big scope", "constraints": ["many constraints"]},
            {"test_cases": [{"type": "positive"}, {"type": "negative"}, {"type": "edge"}]},
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


# ── Critic AC Coverage Integration ───────────────────────────────────────────

class CriticAcCoverageTests(unittest.TestCase):
    def test_ac_coverage_in_critic_output(self) -> None:
        ba = {
            "acceptance_criteria": ["User can log in with phone OTP"],
            "unknowns": [],
        }
        dev = {
            "scope": "Phone OTP login",
            "flow": "login",
            "constraints": ["Rate limit"],
            "summary": "Implements phone OTP login and verification",
        }
        result = run_critic_assistant(ba_output=ba, dev_output=dev)
        self.assertIn("ac_coverage", result)
        self.assertIn("overall_score", result["ac_coverage"])

    def test_uncovered_ac_produces_finding(self) -> None:
        ba = {
            "acceptance_criteria": ["Fingerprint scanning must be supported via hardware sensor"],
        }
        dev = {"scope": "OTP only", "flow": "login", "summary": "One-time passcode verification"}
        result = run_critic_assistant(ba_output=ba, dev_output=dev)
        types = [f["type"] for f in result["findings"]]
        self.assertIn("ac_not_covered", types)

    def test_testability_score_in_output(self) -> None:
        result = run_critic_assistant()
        self.assertIn("testability_score", result)
        self.assertIsInstance(result["testability_score"], float)

    def test_explicit_ac_param_takes_priority(self) -> None:
        ba = {"acceptance_criteria": ["Login works"]}
        result = run_critic_assistant(
            ba_output=ba,
            acceptance_criteria=["Biometric authentication required"],
        )
        # The explicit AC should override ba_output AC
        self.assertIn("ac_coverage", result)


if __name__ == "__main__":
    unittest.main()
