"""Tests for structured assistant stage outputs."""

import unittest

from backend.assistants import (
    run_app_ui_assistant,
    run_ba_assistant,
    run_critic_assistant,
    run_dev_assistant,
    run_test_assistant,
)


class AssistantTests(unittest.TestCase):
    def test_ba_assistant_outputs_required_keys(self) -> None:
        output = run_ba_assistant(
            {
                "title": "Add a login screen with phone number",
                "description": "User should sign in with phone number.",
                "acceptanceCriteria": "Phone number is required.",
                "tags": ["auth"],
            },
            {
                "refined_base_flow": "login",
                "refined_variant": "phone_number",
                "refined_fields": ["phone_number"],
                "refined_validations": ["required", "phone_format"],
            },
        )
        self.assertEqual(output["assistant"], "ba")
        self.assertIn("refined_requirement", output)
        self.assertIn("acceptance_criteria", output)
        self.assertEqual(output["variant"], "phone_number")

    def test_ui_assistant_outputs_fields_and_states(self) -> None:
        ba_output = {
            "refined_requirement": "Add a login screen with phone number.",
            "flows": ["login"],
            "variant": "phone_number",
            "unknowns": [],
        }
        output = run_app_ui_assistant(
            ba_output,
            {
                "refined_surface": "ui_screen",
                "refined_fields": ["phone_number"],
                "refined_validations": ["required", "phone_format"],
            },
        )
        self.assertEqual(output["assistant"], "app_ui")
        self.assertTrue(output["fields"])
        self.assertIn("loading", output["states"])

    def test_dev_assistant_outputs_execution_packet(self) -> None:
        ba_output = {
            "refined_requirement": "Fix login validation.",
            "flows": ["login"],
            "variant": None,
            "business_rules": ["Do not bypass credential validation."],
            "acceptance_criteria": ["Email must use a valid format."],
            "unknowns": [],
        }
        ui_output = {
            "screen_name": "Login Form",
            "screen_type": "form",
            "fields": [{"name": "email", "validation": ["required", "email_format"]}],
            "actions": ["submit"],
            "skippable": False,
        }
        repo_context = {
            "related_flows": ["session"],
            "likely_bug_hotspots": [{"file": "ui/LoginScreen.kt", "flow": "login", "role": "ui", "reasons": ["matches current file"]}],
            "session_bias_summary": {"current_file": "ui/LoginScreen.kt"},
            "open_files": ["ui/LoginScreen.kt"],
        }
        output = run_dev_assistant(ba_output, ui_output, repo_context, {"refined_surface": "ui_validation"})
        self.assertEqual(output["assistant"], "dev")
        self.assertIn("# Task", output["execution_packet"])
        self.assertTrue(output["selected_files"])

    def test_test_assistant_creates_positive_negative_and_edge_cases(self) -> None:
        ba_output = {"flows": ["login"], "acceptance_criteria": ["Phone is required."], "unknowns": []}
        dev_output = {"flow": "login"}
        ui_output = {"fields": [{"name": "phone_number"}], "skippable": False}
        output = run_test_assistant(ba_output, dev_output, ui_output)
        case_types = {case["type"] for case in output["test_cases"]}
        self.assertIn("positive", case_types)
        self.assertIn("negative", case_types)
        self.assertIn("edge", case_types)

    def test_critic_detects_phone_login_email_password_conflict(self) -> None:
        ba_output = {"variant": "phone_number", "acceptance_criteria": ["Use phone login."], "unknowns": []}
        ui_output = {
            "fields": [{"name": "email"}, {"name": "password"}],
            "screen_type": "form",
            "unknowns": [],
            "skippable": False,
        }
        dev_output = {"variant": "phone_number", "flow": "login", "surface": "ui_form", "task_summary": "Fix email and password login."}
        critic = run_critic_assistant(ba_output=ba_output, ui_output=ui_output, dev_output=dev_output)
        self.assertTrue(any(item["type"] == "conflict" for item in critic["findings"]))


if __name__ == "__main__":
    unittest.main()
