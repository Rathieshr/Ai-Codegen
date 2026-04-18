"""Tests for importance-aware prompt building."""

import unittest

from context_builder.builder import (
    ContextBuilder,
    compress_flow_steps,
    compress_plan,
    select_bug_fix_constraints,
    select_bug_fix_flow,
)
from logic_store.store import LogicStore


class FakeLogicStore:
    """Small in-memory logic store for builder tests."""

    def find_relevant(self, query: str) -> list[dict]:
        return [
            {
                "id": "mixed_flow",
                "name": "Mixed Flow",
                "summary": "A flow with critical and low-priority steps.",
                "steps": [
                    "Show UI hint",
                    "Record analytics event",
                    "Verify password before issuing token",
                    "Store data in database",
                ],
                "services": ["AuthService", "AnalyticsService"],
                "dependencies": ["session_token_factory"],
                "files": ["backend/auth.py"],
                "snippets": [
                    {
                        "label": "token contract",
                        "code": "return {\"token\": token}",
                    }
                ],
            }
        ]


class CriticalOverflowLogicStore:
    """Logic store where critical steps cannot fit into tiny budgets."""

    def find_relevant(self, query: str) -> list[dict]:
        return [
            {
                "id": "critical_overflow",
                "name": "Critical Overflow",
                "summary": "A flow with many critical steps.",
                "steps": [
                    "Complete payment transaction",
                    "Issue login token",
                    "Verify password reset token",
                    "Show UI hint",
                ],
                "services": [],
                "dependencies": [],
                "files": [],
                "snippets": [],
            }
        ]


class ContextBuilderTests(unittest.TestCase):
    def test_prompt_includes_importance_aware_flow(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt("Add login feature")

        prompt = result["optimized_prompt"]

        self.assertIn("## Detected Intent: feature", prompt)
        self.assertIn("## Flow", prompt)
        self.assertIn("## Critical Steps", prompt)
        self.assertIn("Verify password before issuing token", prompt)
        self.assertIn("Store data in database", prompt)
        self.assertNotIn("## Importance-Aware Flow", prompt)
        self.assertNotIn("## Composed Flow", prompt)

    def test_reduced_prompt_removes_low_priority_steps_first(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt(
            "Explain login flow",
            max_tokens=200,
        )

        prompt = result["optimized_prompt"]

        self.assertIn("Verify password before issuing token", prompt)
        self.assertIn("Store data in database", prompt)

    def test_full_prompt_keeps_existing_metadata_and_snippets(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt(
            "Add login feature",
            max_tokens=900,
        )

        prompt = result["optimized_prompt"]

        self.assertIn("## Level 2: Metadata", prompt)
        self.assertIn("## Level 3: Minimal Snippets", prompt)
        self.assertIn("return {\"token\": token}", prompt)

    def test_bug_fix_prompt_marks_intent_and_boosts_validation(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt("Fix login bug")

        prompt = result["optimized_prompt"]

        self.assertIn("## Detected Intent: bug_fix", prompt)
        self.assertIn("## Constraints", prompt)
        self.assertIn("Do not bypass credential validation.", prompt)
        self.assertIn("Verify password before issuing token", prompt)
        self.assertIn("## Plan", prompt)
        self.assertIn("Identify root cause in the relevant flow", prompt)
        self.assertIn("Identify root cause before applying fix", prompt)
        self.assertIn("Do not change working auth/session logic unnecessarily.", prompt)
        self.assertNotIn("## Level 3: Minimal Snippets", prompt)
        self.assertNotIn("## Level 2: Metadata", prompt)
        self.assertLess(prompt.index("## Constraints"), prompt.index("# Execution Rules"))

    def test_plan_metadata_and_prompt_section_are_included_for_risky_task(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt("Add OTP login")

        prompt = result["optimized_prompt"]

        self.assertTrue(result["planning_enabled"])
        self.assertTrue(result["plan"]["needs_planning"])
        self.assertIn("implementation plan with 4 steps", result["plan_summary"])
        self.assertIn("## Plan", prompt)
        self.assertIn("Analyze existing login and session flow", prompt)
        self.assertIn("(risk: high)", prompt)
        self.assertNotIn("Purpose:", prompt)
        self.assertLess(prompt.index("## Constraints"), prompt.index("## Plan"))
        self.assertLess(prompt.index("## Plan"), prompt.index("# Execution Rules"))

    def test_plan_section_omitted_for_simple_explain_task(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt("Explain login flow")

        self.assertFalse(result["planning_enabled"])
        self.assertEqual(result["plan"]["plan_type"], "none")
        self.assertNotIn("## Plan", result["optimized_prompt"])

    def test_feature_prompt_preserves_full_flow_under_reduction(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt(
            "Add signup feature",
            max_tokens=500,
        )

        prompt = result["optimized_prompt"]

        self.assertIn("Show UI hint", prompt)
        self.assertIn("Record analytics event", prompt)
        self.assertIn("Verify password before issuing token", prompt)
        self.assertIn("Store data in database", prompt)

    def test_tiny_budget_never_removes_critical_steps(self) -> None:
        result = ContextBuilder(CriticalOverflowLogicStore()).build_prompt(
            "Add secure checkout login",
            max_tokens=20,
        )

        prompt = result["optimized_prompt"]

        self.assertIn("Complete payment transaction", prompt)
        self.assertIn("Issue login token", prompt)
        self.assertIn("Verify password reset token", prompt)
        self.assertNotIn("Show UI hint", prompt)

    def test_tiny_budget_preserves_critical_step_order(self) -> None:
        result = ContextBuilder(CriticalOverflowLogicStore()).build_prompt(
            "Add secure checkout login",
            max_tokens=20,
        )

        prompt = result["optimized_prompt"]

        first = prompt.index("Complete payment transaction")
        second = prompt.index("Issue login token")
        third = prompt.index("Verify password reset token")
        self.assertLess(first, second)
        self.assertLess(second, third)

    def test_real_login_flow_injects_linked_dependency_flow(self) -> None:
        result = ContextBuilder(LogicStore()).build_prompt(
            "Add login feature",
            max_tokens=900,
        )

        prompt = result["optimized_prompt"]

        self.assertIn("## Linked Flows", prompt)
        self.assertIn("Login Flow → TokenGeneration", prompt)
        self.assertIn("## Impacted Components", prompt)
        self.assertIn("LoginController (controller)", prompt)
        self.assertIn("AuthService (service)", prompt)
        self.assertIn("TokenGeneration (flow)", prompt)
        self.assertIn("## Flow", prompt)
        self.assertIn("## Constraints", prompt)
        self.assertIn("Reuse existing token/session lifecycle logic.", prompt)
        self.assertIn("Generate session token with user id, expiry, and login reason.", prompt)
        session_step = prompt.index(
            "Login validates credentials, blocks inactive users, records an audit event, then returns a session token."
        )
        dependency_step = prompt.index("Generate session token with user id, expiry, and login reason.")
        otp_step = prompt.index(
            "OTP login should reuse the existing identity lookup and session creation path"
        )
        self.assertLess(prompt.index("## Linked Flows"), prompt.index("## Impacted Components"))
        self.assertLess(session_step, dependency_step)
        self.assertLess(dependency_step, otp_step)

    def test_unrelated_flow_omits_impacted_components(self) -> None:
        result = ContextBuilder(FakeLogicStore()).build_prompt(
            "Explain mixed flow",
            max_tokens=900,
        )

        self.assertNotIn("## Impacted Components", result["optimized_prompt"])

    def test_flow_steps_compress_into_ordered_chain(self) -> None:
        self.assertEqual(
            compress_flow_steps(["Validate", "check status", "create session", "generate token"]),
            ["Validate -> check status -> create session -> generate token"],
        )

    def test_plan_compression_keeps_risk_without_purpose(self) -> None:
        plan = {
            "needs_planning": True,
            "steps": [
                {
                    "title": "Analyze login/session flow",
                    "purpose": "Long purpose",
                    "risk": "medium",
                }
            ],
        }

        self.assertEqual(compress_plan(plan), ["1. Analyze login/session flow (risk: medium)"])

    def test_feature_prompt_has_more_context_than_bug_fix_prompt(self) -> None:
        builder = ContextBuilder(LogicStore())

        feature = builder.build_prompt("Add login feature", max_tokens=900)
        bug_fix = builder.build_prompt("Fix login bug", max_tokens=900)

        self.assertGreater(feature["token_estimate"], bug_fix["token_estimate"])
        self.assertIn("## Level 3: Minimal Snippets", feature["optimized_prompt"])
        self.assertNotIn("## Level 3: Minimal Snippets", bug_fix["optimized_prompt"])
        self.assertIn("Identify root cause in the relevant flow", bug_fix["optimized_prompt"])

    def test_bug_fix_flow_is_narrower_than_feature_flow(self) -> None:
        builder = ContextBuilder(LogicStore())

        feature = builder.build_prompt("Add login feature", max_tokens=900)["optimized_prompt"]
        bug_fix = builder.build_prompt("Fix login bug", max_tokens=900)["optimized_prompt"]

        self.assertIn("OTP login should reuse", feature)
        self.assertIn("Failed authentication attempts", feature)
        self.assertNotIn("OTP login should reuse", bug_fix)
        self.assertNotIn("Failed authentication attempts", bug_fix)
        self.assertIn("Reuse existing token/session lifecycle logic.", bug_fix)

    def test_login_ui_bug_fix_stays_compact_and_safe(self) -> None:
        result = ContextBuilder(LogicStore()).build_prompt("fix the login ui flow", max_tokens=900)
        prompt = result["optimized_prompt"]

        self.assertEqual(result["matched_logic"], ["Login"])
        self.assertLess(result["token_estimate"], 250)
        self.assertEqual(result["plan"]["plan_type"], "bug_fix")
        self.assertEqual(len(result["plan"]["steps"]), 2)
        self.assertIn("## Detected Intent: bug_fix", prompt)
        self.assertIn("Keep failed authentication responses generic.", prompt)
        self.assertIn("Reuse existing token/session lifecycle logic.", prompt)
        self.assertIn("Identify root cause before applying fix", prompt)
        self.assertNotIn("## Level 3: Minimal Snippets", prompt)
        self.assertNotIn("TokenGeneration (flow)", prompt)

    def test_select_bug_fix_flow_keeps_core_auth_steps_only(self) -> None:
        selected = select_bug_fix_flow(
            [
                "Validate credentials",
                "Check account status",
                "Create session",
                "Generate token",
            ]
        )

        self.assertEqual(
            selected,
            ["Validate credentials", "Check account status", "Reuse existing session/token logic."],
        )

    def test_select_bug_fix_constraints_keeps_critical_auth_session_rules(self) -> None:
        selected = select_bug_fix_constraints(
            [
                "Do not create duplicate user records.",
                "Keep failed authentication responses generic.",
                "Reuse existing token/session lifecycle logic.",
                "Preserve password hashing and validation rules.",
            ]
        )

        self.assertEqual(
            selected,
            [
                "Keep failed authentication responses generic.",
                "Reuse existing token/session lifecycle logic.",
                "Preserve password hashing and validation rules.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
