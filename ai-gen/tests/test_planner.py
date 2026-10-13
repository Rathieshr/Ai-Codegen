"""Tests for deterministic ai-gen planning heuristics."""

import unittest

from backend.planner import create_plan, should_plan, summarize_plan


class PlannerTests(unittest.TestCase):
    def test_should_plan_false_for_simple_explain_query(self) -> None:
        self.assertFalse(should_plan("Explain login flow", intent="general"))

    def test_should_plan_true_for_add_otp_login(self) -> None:
        self.assertTrue(should_plan("Add OTP login", intent="feature"))

    def test_should_plan_true_for_refactor_auth_flow(self) -> None:
        self.assertTrue(should_plan("Refactor auth flow", intent="refactor"))

    def test_create_plan_returns_deterministic_auth_otp_steps(self) -> None:
        plan = create_plan(
            "Add OTP login",
            intent="feature",
            linked_flows=["Login Flow", "TokenGeneration"],
            constraints=["Reuse the existing token/session generation path."],
        )

        self.assertTrue(plan["needs_planning"])
        self.assertEqual(plan["plan_type"], "implementation")
        self.assertEqual(len(plan["steps"]), 4)
        self.assertEqual(plan["steps"][0]["id"], "step_1")
        self.assertEqual(plan["steps"][0]["title"], "Analyze existing login and session flow")
        self.assertEqual(plan["steps"][1]["risk"], "high")
        self.assertIn("OTP validation", plan["steps"][1]["title"])
        self.assertIn("token or session", plan["steps"][2]["title"])

    def test_create_plan_returns_none_for_non_plan_task(self) -> None:
        plan = create_plan("Summarize auth logic", intent="general")

        self.assertFalse(plan["needs_planning"])
        self.assertEqual(plan["plan_type"], "none")
        self.assertEqual(plan["steps"], [])
        self.assertEqual(summarize_plan(plan), "Planning not required.")

    def test_refactor_plan_uses_impacted_components_signal(self) -> None:
        plan = create_plan(
            "Improve auth structure",
            intent="refactor",
            impacted_components=["LoginController (controller)", "AuthService (service)"],
        )

        self.assertTrue(plan["needs_planning"])
        self.assertEqual(plan["plan_type"], "refactor")
        self.assertIn("refactor", summarize_plan(plan))

    def test_bug_fix_plan_is_minimal(self) -> None:
        plan = create_plan(
            "Fix login bug",
            intent="bug_fix",
            linked_flows=["Login Flow", "TokenGeneration"],
            constraints=["Reuse existing token/session lifecycle logic."],
        )

        self.assertTrue(plan["needs_planning"])
        self.assertEqual(plan["plan_type"], "bug_fix")
        self.assertEqual(len(plan["steps"]), 2)
        self.assertIn("Identify root cause", plan["steps"][0]["title"])


if __name__ == "__main__":
    unittest.main()
