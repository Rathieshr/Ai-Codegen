"""Tests for refinement decision heuristics."""

import unittest
from unittest.mock import patch

from backend.refinement.refinement_decider import should_use_refiner


class RefinementDeciderTests(unittest.TestCase):
    def test_azure_devops_medium_confidence_triggers_refinement(self) -> None:
        with patch("backend.refinement.refinement_decider.get_refinement_provider") as mocked:
            mocked.return_value.is_enabled.return_value = True
            use_refiner, reason = should_use_refiner(
                source="azure_devops",
                intent="bug_fix",
                detected_flow="",
                confidence_level="medium",
                query="Fix login regex validation issue",
                work_item={"title": "Fix login regex validation issue"},
            )

        self.assertEqual(use_refiner, True)
        self.assertIn("azure devops", reason)

    def test_high_confidence_explain_skips_refinement(self) -> None:
        with patch("backend.refinement.refinement_decider.get_refinement_provider") as mocked:
            mocked.return_value.is_enabled.return_value = True
            use_refiner, reason = should_use_refiner(
                source="vscode",
                intent="general",
                detected_flow="login",
                confidence_level="high",
                query="Explain login flow",
            )

        self.assertEqual(use_refiner, False)
        self.assertIn("response task", reason)

    def test_variant_words_trigger_refinement_for_weak_context(self) -> None:
        with patch("backend.refinement.refinement_decider.get_refinement_provider") as mocked:
            mocked.return_value.is_enabled.return_value = True
            use_refiner, reason = should_use_refiner(
                source="vscode",
                intent="feature",
                detected_flow="",
                confidence_level="low",
                query="Add a login screen with phone number",
            )

        self.assertEqual(use_refiner, True)
        self.assertIn("variant-heavy", reason)

    def test_disabled_provider_skips_refinement(self) -> None:
        with patch("backend.refinement.refinement_decider.get_refinement_provider", return_value=None):
            use_refiner, reason = should_use_refiner(
                source="azure_devops",
                intent="bug_fix",
                detected_flow="",
                confidence_level="low",
                query="Fix login validation issue",
            )

        self.assertEqual(use_refiner, False)
        self.assertEqual(reason, "refiner disabled")


if __name__ == "__main__":
    unittest.main()
