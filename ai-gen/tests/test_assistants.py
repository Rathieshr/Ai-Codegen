"""Tests for structured assistant stage outputs."""

import unittest
from unittest.mock import Mock, patch

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
                "base_flows": ["login", "otp_verification"],
                "variants": ["phone_otp"],
                "refined_fields": ["phone_number"],
                "fields": ["phone_number", "otp"],
                "refined_validations": ["required", "phone_format"],
            },
        )
        self.assertEqual(output["assistant"], "ba")
        self.assertIn("refined_requirement", output)
        self.assertIn("acceptance_criteria", output)
        self.assertEqual(output["variant"], "phone_otp")
        self.assertEqual(output["flows"], ["login", "otp_verification"])

    def test_ba_assistant_resolves_answered_otp_unknowns_from_review_feedback(self) -> None:
        output = run_ba_assistant(
            {
                "title": "Ai Gen Extension Test",
                "description": "Focus first on phone number input and otp verification step.",
                "acceptanceCriteria": "",
                "tags": ["auth"],
            },
            {
                "base_flows": ["login", "otp_verification"],
                "variants": ["phone_otp"],
                "fields": ["phone_number", "otp"],
            },
            {
                "review_feedback": [
                    {
                        "comment": "yes retry policy 3 times max. second factor needed after primary input succeeds. yes otp is needed"
                    }
                ],
                "critic_findings": [
                    {
                        "severity": "blocking",
                        "message": "Clarify OTP retry and expiry policy.",
                    },
                    {
                        "severity": "blocking",
                        "message": "Is OTP or a second-factor step required after the primary input succeeds?",
                    },
                ],
            },
        )
        self.assertNotIn("Is OTP or a second-factor step required after the primary input succeeds?", output["unknowns"])
        self.assertNotIn("Clarify OTP retry and expiry policy.", output["unknowns"])
        self.assertIn("Review clarifications", output["refined_requirement"])

    def test_ba_assistant_resolves_second_factor_screen_wording(self) -> None:
        output = run_ba_assistant(
            {
                "title": "Ai Gen Extension Test",
                "description": "Focus first on phone number input and otp verification step.",
                "acceptanceCriteria": "",
                "tags": ["auth"],
            },
            {
                "base_flows": ["login", "otp_verification"],
                "variants": ["phone_otp"],
                "fields": ["phone_number", "otp"],
            },
            {
                "review_feedback": [
                    {
                        "comment": "retry policy of 3 times and expiry policy of 60 seconds. second factor screen required"
                    }
                ],
                "critic_findings": [
                    {
                        "severity": "blocking",
                        "message": "Clarify OTP retry and expiry policy.",
                    },
                    {
                        "severity": "blocking",
                        "message": "Is OTP or a second-factor step required after the primary input succeeds?",
                    },
                ],
            },
        )
        self.assertEqual(output["unknowns"], [])

    def test_ba_assistant_can_use_phi_to_resolve_large_clarification_text(self) -> None:
        provider = Mock()
        provider.is_enabled.return_value = True
        provider.refine_json.return_value = {"answered": True, "confidence": "high"}
        with patch("backend.assistants.ba_assistant.get_refinement_provider", return_value=provider):
            output = run_ba_assistant(
                {
                    "title": "Ai Gen Extension Test",
                    "description": "Focus first on phone number input and otp verification step.",
                    "acceptanceCriteria": "",
                    "tags": ["auth"],
                },
                {
                    "base_flows": ["login", "otp_verification"],
                    "variants": ["phone_otp"],
                    "fields": ["phone_number", "otp"],
                },
                {
                    "review_feedback": [
                        {
                            "comment": (
                                "After the primary phone entry succeeds, route the user into a dedicated secondary "
                                "verification screen backed by a one-time passcode challenge with a 60-second expiry "
                                "window and no more than three retries before lockout messaging."
                            )
                        }
                    ],
                    "critic_findings": [
                        {
                            "severity": "blocking",
                            "message": "Clarify OTP retry and expiry policy.",
                        },
                        {
                            "severity": "blocking",
                            "message": "Is OTP or a second-factor step required after the primary input succeeds?",
                        },
                    ],
                },
            )

        self.assertEqual(output["unknowns"], [])
        self.assertTrue(provider.refine_json.called)

    def test_ui_assistant_outputs_fields_and_states(self) -> None:
        ba_output = {
            "refined_requirement": "Add a login screen with phone number.",
            "flows": ["login", "otp_verification"],
            "variant": "phone_otp",
            "variants": ["phone_otp"],
            "unknowns": [],
        }
        output = run_app_ui_assistant(
            ba_output,
            {
                "surfaces": ["ui_screen"],
                "fields": ["phone_number", "otp"],
                "refined_validations": ["required", "phone_format"],
            },
        )
        self.assertEqual(output["assistant"], "app_ui")
        self.assertTrue(output["fields"])
        self.assertIn("loading", output["states"])
        self.assertEqual([field["name"] for field in output["fields"]], ["phone_number", "otp"])
        self.assertEqual(
            output["summary"],
            "Design login UI with phone number entry, OTP request, OTP verification state, validation and error handling.",
        )

    def test_dev_assistant_outputs_execution_packet(self) -> None:
        ba_output = {
            "refined_requirement": "Fix login validation.",
            "flows": ["login", "otp_verification"],
            "variant": None,
            "variants": ["phone_otp"],
            "business_rules": ["Do not bypass credential validation."],
            "acceptance_criteria": ["Email must use a valid format."],
            "unknowns": [],
        }
        ui_output = {
            "screen_name": "Login Form",
            "screen_type": "form",
            "fields": [{"name": "phone_number", "validation": ["required", "format"]}, {"name": "otp", "validation": ["required"]}],
            "actions": ["submit"],
            "skippable": False,
        }
        repo_context = {
            "related_flows": ["session"],
            "likely_bug_hotspots": [{"file": "ui/LoginScreen.kt", "flow": "login", "role": "ui", "reasons": ["matches current file"]}],
            "session_bias_summary": {"current_file": "ui/LoginScreen.kt"},
            "open_files": ["ui/LoginScreen.kt"],
        }
        output = run_dev_assistant(ba_output, ui_output, repo_context, {"surfaces": ["ui_validation"], "variants": ["phone_otp"]})
        self.assertEqual(output["assistant"], "dev")
        self.assertIn("# Task", output["execution_packet"])
        self.assertTrue(output["selected_files"])
        self.assertIn("phone_otp", output["variants"])

    def test_test_assistant_creates_positive_negative_and_edge_cases(self) -> None:
        ba_output = {"flows": ["login", "otp_verification"], "variants": ["phone_otp"], "acceptance_criteria": ["Phone is required."], "unknowns": []}
        dev_output = {"flow": "login", "variants": ["phone_otp"]}
        ui_output = {"fields": [{"name": "phone_number"}, {"name": "otp"}], "skippable": False}
        output = run_test_assistant(ba_output, dev_output, ui_output)
        case_types = {case["type"] for case in output["test_cases"]}
        self.assertIn("positive", case_types)
        self.assertIn("negative", case_types)
        self.assertIn("edge", case_types)

    def test_critic_detects_phone_login_email_password_conflict(self) -> None:
        ba_output = {"variant": "phone_otp", "variants": ["phone_otp"], "acceptance_criteria": ["Use phone login."], "unknowns": []}
        ui_output = {
            "fields": [{"name": "email"}, {"name": "password"}],
            "screen_type": "form",
            "unknowns": [],
            "skippable": False,
        }
        dev_output = {"variant": "phone_otp", "variants": ["phone_otp", "email_password"], "flow": "login", "surfaces": ["ui_screen"], "surface": "ui_form", "task_summary": "Fix email and password login."}
        critic = run_critic_assistant(ba_output=ba_output, ui_output=ui_output, dev_output=dev_output)
        finding_types = {item["type"] for item in critic["findings"]}
        self.assertIn("conflict", finding_types)
        self.assertIn("missing_critical_field", finding_types)
        severities = {item["severity"] for item in critic["findings"]}
        self.assertIn("blocking", severities)


if __name__ == "__main__":
    unittest.main()
