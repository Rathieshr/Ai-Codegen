"""Tests for refinement schema validation."""

import unittest

from backend.refinement.schema_validator import validate_task_refinement


class SchemaValidatorTests(unittest.TestCase):
    def test_unknown_keys_removed_and_missing_lists_default(self) -> None:
        validated = validate_task_refinement({"base_flow": " login ", "invented": "x"})

        self.assertEqual(validated["base_flow"], "login")
        self.assertEqual(validated["fields"], [])
        self.assertNotIn("invented", validated)

    def test_confidence_clamped(self) -> None:
        validated = validate_task_refinement({"confidence": "extreme"})

        self.assertEqual(validated["confidence"], "low")

    def test_long_lists_truncated(self) -> None:
        validated = validate_task_refinement(
            {
                "fields": [f"field_{index}" for index in range(20)],
                "first_pass_scope": [f"scope_{index}" for index in range(20)],
            }
        )

        self.assertEqual(len(validated["fields"]), 10)
        self.assertEqual(len(validated["first_pass_scope"]), 8)

    def test_commands_and_file_paths_removed(self) -> None:
        validated = validate_task_refinement(
            {
                "fields": ["email", "src/LoginScreen.kt", "rm -rf /tmp"],
                "unknowns": ["bash deploy.sh", "Need OTP?"],
            }
        )

        self.assertEqual(validated["fields"], ["email"])
        self.assertEqual(validated["unknowns"], ["Need OTP?"])


if __name__ == "__main__":
    unittest.main()
