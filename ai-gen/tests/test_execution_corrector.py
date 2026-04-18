"""Tests for deterministic execution retry correction."""

import unittest

from backend.execution_corrector import build_corrected_execution_prompt, generate_retry_plan


class ExecutionCorrectorTests(unittest.TestCase):
    def test_drift_triggers_retry_with_narrowed_files(self) -> None:
        plan = generate_retry_plan(
            validation_result={"out_of_scope_files": ["docs/readme.md"], "constraint_violations": [], "risky_changes": []},
            original_execution_context={"constraints": [], "likely_breakpoints": ["ui/LoginScreen.kt"]},
            selected_files=["ui/LoginScreen.kt", "docs/readme.md"],
            detected_flow="login",
            related_flows=["session"],
        )

        self.assertEqual(plan["strategy"], "narrow_scope")
        self.assertEqual(plan["corrected_files"], ["ui/LoginScreen.kt"])
        self.assertIn("Do not modify files outside this list.", plan["adjusted_instructions"])

    def test_constraint_violation_reinforces_constraints(self) -> None:
        plan = generate_retry_plan(
            validation_result={
                "out_of_scope_files": [],
                "constraint_violations": ["Possible user-existence leak in authentication error handling."],
                "risky_changes": [],
            },
            original_execution_context={
                "constraints": ["Keep failed authentication responses generic."],
                "likely_breakpoints": [],
            },
            selected_files=["backend/auth.py"],
            detected_flow="login",
            related_flows=[],
        )

        self.assertEqual(plan["strategy"], "constraint_enforcement")
        self.assertTrue(plan["reinforced_constraints"][0].startswith("Previous attempt violated constraint:"))
        self.assertIn("Treat reinforced constraints as non-negotiable.", plan["adjusted_instructions"])

    def test_risky_changes_trigger_scope_reduction(self) -> None:
        plan = generate_retry_plan(
            validation_result={
                "out_of_scope_files": [],
                "constraint_violations": [],
                "risky_changes": ["Auth-sensitive file changed: backend/auth.py"],
            },
            original_execution_context={"constraints": [], "likely_breakpoints": ["ui/LoginScreen.kt"]},
            selected_files=["backend/auth.py", "ui/LoginScreen.kt"],
            detected_flow="login",
            related_flows=[],
        )

        self.assertEqual(plan["strategy"], "focus_breakpoints")
        self.assertIn("Avoid touching auth/payment/session unless necessary.", plan["adjusted_instructions"])

    def test_no_issues_requires_no_retry(self) -> None:
        plan = generate_retry_plan(
            validation_result={"out_of_scope_files": [], "constraint_violations": [], "risky_changes": []},
            original_execution_context={"constraints": [], "likely_breakpoints": []},
            selected_files=["ui/LoginScreen.kt"],
            detected_flow="login",
            related_flows=[],
        )

        self.assertEqual(plan["retry_required"], False)
        self.assertEqual(plan["strategy"], "none")

    def test_corrected_prompt_contains_previous_issues_and_retry_rules(self) -> None:
        plan = {
            "retry_required": True,
            "corrected_files": ["ui/LoginScreen.kt"],
            "reinforced_constraints": ["Previous attempt violated constraint: Possible validation bypass."],
            "adjusted_instructions": ["Do not repeat previous mistakes.", "Strictly follow the corrected file scope."],
        }

        prompt = build_corrected_execution_prompt(
            query="Fix login UI flow",
            retry_plan=plan,
            detected_flow="login",
            related_flows=["session"],
            previous_issues=["constraint violation detected"],
        )

        self.assertIn("Fix login UI flow (retry)", prompt)
        self.assertIn("# Constraints (Reinforced)", prompt)
        self.assertIn("# Previous Issues", prompt)
        self.assertIn("# Retry Instructions", prompt)


if __name__ == "__main__":
    unittest.main()
