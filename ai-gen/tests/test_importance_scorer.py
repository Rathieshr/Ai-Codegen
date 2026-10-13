"""Tests for deterministic business importance scoring."""

import unittest

from backend.importance_scorer import (
    extract_critical,
    score_flow,
    score_step,
    sort_by_importance,
    trim_flow,
)


class ImportanceScorerTests(unittest.TestCase):
    def test_scores_auth_keywords_as_critical(self) -> None:
        scored = score_step("Verify password before issuing token")

        self.assertGreaterEqual(scored["importance"], 0.9)
        self.assertIn("password", scored["matched_keywords"])
        self.assertIn("token", scored["matched_keywords"])
        self.assertIn("verify", scored["matched_keywords"])

    def test_scores_low_priority_keywords(self) -> None:
        self.assertEqual(score_step("Show UI hint")["importance"], 0.2)
        self.assertLess(score_step("Record analytics event")["importance"], 0.3)

    def test_scores_validation_variants(self) -> None:
        scored = score_step("Validates request payload")

        self.assertGreaterEqual(scored["importance"], 0.8)
        self.assertIn("validation", scored["matched_keywords"])

    def test_bug_fix_intent_boosts_validation(self) -> None:
        general = score_step("Validate input", intent="general")
        bug_fix = score_step("Validate input", intent="bug_fix")

        self.assertGreater(bug_fix["importance"], general["importance"])

    def test_bug_fix_intent_boosts_error_handling(self) -> None:
        general = score_step("Handle error response", intent="general")
        bug_fix = score_step("Handle error response", intent="bug_fix")

        self.assertGreater(bug_fix["importance"], general["importance"])

    def test_refactor_intent_boosts_dependencies(self) -> None:
        general = score_step("Review service dependencies", intent="general")
        refactor = score_step("Review service dependencies", intent="refactor")

        self.assertGreater(refactor["importance"], general["importance"])

    def test_generate_token_scores_above_critical_threshold(self) -> None:
        scored = score_step("Generate token")

        self.assertGreater(scored["importance"], 0.9)
        self.assertIn("token", scored["matched_keywords"])

    def test_log_event_scores_low(self) -> None:
        scored = score_step("Log event")

        self.assertLess(scored["importance"], 0.4)

    def test_generate_token_scores_higher_than_log_token(self) -> None:
        generated = score_step("Generate token")
        logged = score_step("Log token")

        self.assertGreater(generated["importance"], logged["importance"])

    def test_validate_payment_scores_higher_than_validate_ui(self) -> None:
        payment = score_step("Validate payment")
        ui = score_step("Validate UI")

        self.assertGreater(payment["importance"], ui["importance"])

    def test_does_not_match_short_keywords_inside_other_words(self) -> None:
        scored = score_step("Verify password before issuing token")

        self.assertNotIn("ui", scored["matched_keywords"])

    def test_sort_by_importance_descending(self) -> None:
        scored = score_flow(
            [
                "Show UI hint",
                "Persist data",
                "Complete payment transaction",
            ]
        )

        sorted_steps = sort_by_importance(scored)

        self.assertEqual(sorted_steps[0]["step"], "Complete payment transaction")
        self.assertEqual(sorted_steps[-1]["step"], "Show UI hint")

    def test_extract_critical_keeps_original_order(self) -> None:
        scored = score_flow(
            [
                "Complete payment transaction",
                "Show UI hint",
                "Issue login token",
            ]
        )

        critical_steps = extract_critical(scored)

        self.assertEqual(
            [step["step"] for step in critical_steps],
            ["Complete payment transaction", "Issue login token"],
        )

    def test_trim_flow_removes_lowest_importance_first_but_keeps_order(self) -> None:
        scored = score_flow(
            [
                "Show UI hint",
                "Record analytics event",
                "Verify password before issuing token",
                "Store data in database",
            ]
        )

        trimmed_steps = trim_flow(scored, max_steps=2)

        self.assertEqual(
            [step["step"] for step in trimmed_steps],
            [
                "Verify password before issuing token",
                "Store data in database",
            ],
        )

    def test_trim_flow_never_removes_critical_steps(self) -> None:
        scored = score_flow(
            [
                "Complete payment transaction",
                "Issue login token",
                "Show UI hint",
            ]
        )

        trimmed_steps = trim_flow(scored, max_steps=1)

        self.assertEqual(
            [step["step"] for step in trimmed_steps],
            ["Complete payment transaction", "Issue login token"],
        )


if __name__ == "__main__":
    unittest.main()
