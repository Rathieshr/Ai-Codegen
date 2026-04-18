"""Tests for prompt mode selection and execution confidence."""

import unittest

from backend.execution_mode import detect_prompt_mode, score_execution_confidence


class ExecutionModeTests(unittest.TestCase):
    def test_explain_query_uses_respond_mode(self) -> None:
        mode = detect_prompt_mode(
            query="Explain login flow",
            intent="general",
            matched_logic="Login",
            detected_flow="login",
        )

        self.assertEqual(mode["mode"], "respond")

    def test_strong_implementation_query_uses_execute_mode(self) -> None:
        mode = detect_prompt_mode(
            query="Fix login ui flow",
            intent="bug_fix",
            matched_logic="Login",
            detected_flow="login",
            retrieval_bias_applied=True,
            likely_bug_hotspots=[{"file": "ui/LoginScreen.kt"}],
            planning_enabled=True,
            related_flows=["session"],
        )

        self.assertEqual(mode["mode"], "execute")

    def test_weak_architecture_query_uses_explore_mode(self) -> None:
        mode = detect_prompt_mode(
            query="Design new system architecture",
            intent="general",
            matched_logic=None,
            detected_flow=None,
        )

        self.assertEqual(mode["mode"], "explore")

    def test_confidence_scores_high_with_context_signals(self) -> None:
        confidence = score_execution_confidence(
            intent="bug_fix",
            matched_logic="Login",
            detected_flow="login",
            related_flows=["session"],
            planning_enabled=True,
            retrieval_bias_applied=True,
            likely_bug_hotspots=[{"file": "ui/LoginScreen.kt"}],
            critical_constraints=["Reuse existing token/session lifecycle logic."],
        )

        self.assertEqual(confidence["level"], "high")
        self.assertGreaterEqual(confidence["score"], 0.75)
        self.assertIn("bug hotspots available", confidence["signals"])


if __name__ == "__main__":
    unittest.main()
