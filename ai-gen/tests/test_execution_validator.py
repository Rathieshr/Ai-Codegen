"""Tests for deterministic execution validation."""

import tempfile
import unittest
from pathlib import Path

from backend.execution_validator import (
    ExecutionContext,
    detect_risky_changes,
    detect_scope_drift,
    snapshot_selected_files,
    validate_constraints,
    validate_execution,
)


class ExecutionValidatorTests(unittest.TestCase):
    def test_no_drift_when_only_selected_files_changed(self) -> None:
        drift = detect_scope_drift(
            selected_files=["src/LoginScreen.kt"],
            changed_files=["src/LoginScreen.kt"],
        )

        self.assertEqual(drift["out_of_scope_files"], [])
        self.assertEqual(drift["in_scope_files"], ["src/LoginScreen.kt"])
        self.assertEqual(drift["drift_score"], 0.0)

    def test_drift_detected_when_unrelated_file_changed(self) -> None:
        drift = detect_scope_drift(
            selected_files=["src/LoginScreen.kt"],
            changed_files=["src/LoginScreen.kt", "docs/readme.md"],
        )

        self.assertEqual(drift["out_of_scope_files"], ["docs/readme.md"])
        self.assertGreater(drift["drift_score"], 0.0)

    def test_constraint_violation_detected_via_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "auth.py").write_text('raise AuthError("Email exists")\n', encoding="utf-8")

            violations = validate_constraints(
                constraints=["Do not reveal whether the email or username exists on failed authentication."],
                changed_files=["auth.py"],
                repo_root=temp_dir,
            )

        self.assertIn("Possible user-existence leak in authentication error handling.", violations)

    def test_session_reuse_violation_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "session.py").write_text("token = jwt.encode(payload)\n", encoding="utf-8")

            violations = validate_constraints(
                constraints=["Reuse existing token/session lifecycle logic."],
                changed_files=["session.py"],
                repo_root=temp_dir,
            )

        self.assertIn("Possible new token/session generation path instead of reuse.", violations)

    def test_risky_changes_detected(self) -> None:
        risks = detect_risky_changes(["backend/auth.py", "payments/checkout.py", "frontend/LoginScreen.tsx"])

        self.assertTrue(any("Auth-sensitive" in risk for risk in risks))
        self.assertTrue(any("Payment-sensitive" in risk for risk in risks))
        self.assertTrue(any("multiple modules" in risk for risk in risks))

    def test_validate_execution_combines_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "Widget.kt").write_text("class Widget\n", encoding="utf-8")
            baseline = snapshot_selected_files(temp_dir, ["src/Widget.kt"])
            (root / "src" / "Widget.kt").write_text("class WidgetUpdated\n", encoding="utf-8")

            result = validate_execution(
                context=ExecutionContext(
                    selected_files=["src/Widget.kt"],
                    constraints=[],
                    baseline_hashes=baseline,
                ),
                repo_root=temp_dir,
            )

        self.assertEqual(result["out_of_scope_files"], [])
        self.assertEqual(result["drift_detected"], False)
        self.assertIn("within scope", result["summary"])


if __name__ == "__main__":
    unittest.main()
