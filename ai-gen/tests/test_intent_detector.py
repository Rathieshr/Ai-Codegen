"""Tests for deterministic intent detection."""

import unittest

from backend.intent_detector import detect_intent


class IntentDetectorTests(unittest.TestCase):
    def test_detects_bug_fix(self) -> None:
        self.assertEqual(detect_intent("Fix login bug"), "bug_fix")
        self.assertEqual(detect_intent("Resolve API error"), "bug_fix")

    def test_detects_feature(self) -> None:
        self.assertEqual(detect_intent("Add signup feature"), "feature")
        self.assertEqual(detect_intent("Build onboarding flow"), "feature")

    def test_detects_refactor(self) -> None:
        self.assertEqual(detect_intent("Improve auth structure"), "refactor")
        self.assertEqual(detect_intent("Refactor session service"), "refactor")

    def test_defaults_to_general(self) -> None:
        self.assertEqual(detect_intent("Explain login flow"), "general")


if __name__ == "__main__":
    unittest.main()
