"""Tests for task refiner provider integration."""

import unittest
from unittest.mock import patch

from backend.refinement.task_refiner import refine_epic_stage, refine_task


class TaskRefinerTests(unittest.TestCase):
    def test_provider_disabled_returns_fallback_semantic_mapping(self) -> None:
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=None):
            result = refine_task("Add login screen with phone number")

        self.assertEqual(result["semantic_mapping_applied"], True)
        self.assertEqual(result["refinement_used"], True)
        self.assertEqual(result["refinement_source"], "deterministic_fallback")
        self.assertEqual(result["phi_status"], "not_configured")

    def test_mocked_phi_response_returns_validated_refinement(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.refine_json.return_value = {
            "base_flows": ["Sign In", "verification"],
            "variants": ["mobile otp"],
            "surfaces": ["screen"],
            "fields": ["mobile no", "verification code"],
            "validations": ["required", "phone_format", "length_limit"],
            "scope_hints": ["login screen input", "phone validation", "submit action"],
            "unknowns": ["Is OTP required after phone submission?"],
            "confidence": "medium",
            "bad_key": "ignore me",
        }
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_task("Add a login screen with phone number", {"source": "azure_devops"})

        self.assertEqual(result["refinement_used"], True)
        self.assertEqual(result["refinement"]["variants"], ["phone_otp"])
        self.assertEqual(result["refinement"]["base_flows"], ["login", "otp_verification"])
        self.assertEqual(result["refinement"]["fields"], ["phone_number", "otp"])
        self.assertNotIn("bad_key", result["refinement"])

    def test_malformed_phi_response_falls_back_safely(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.refine_json.return_value = {"fields": ["src/LoginScreen.kt", "phone_number"]}
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_task("Add login screen with phone number")

        self.assertEqual(result["refinement_used"], True)
        self.assertEqual(result["refinement"]["fields"], ["phone_number"])

    def test_provider_unavailable_uses_deterministic_fallback(self) -> None:
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=None):
            result = refine_task("mobile number login with sms code")

        self.assertEqual(result["semantic_mapping_applied"], True)
        self.assertEqual(result["refinement_used"], True)
        self.assertEqual(result["refinement_source"], "deterministic_fallback")
        self.assertEqual(result["refinement_provider"], "deterministic_fallback")
        self.assertEqual(result["refinement"]["base_flows"], ["login", "otp_verification"])
        self.assertEqual(result["refinement"]["variants"], ["phone_otp"])
        self.assertEqual(result["refinement"]["fields"], ["phone_number", "otp"])

    def test_no_metadata_keeps_refinement_not_applied(self) -> None:
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=None):
            result = refine_task("")

        self.assertEqual(result["semantic_mapping_applied"], False)
        self.assertEqual(result["refinement_used"], False)
        self.assertEqual(result["refinement_source"], "none")

    def test_unusable_phi_response_keeps_parsed_json_preview_for_diagnostics(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.probe_json.return_value = {
            "http_status": 200,
            "parsed_json": {"domain": "travel", "features": ["booking"]},
            "raw_content": "",
            "raw_response_preview": "",
        }
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_task("WhatsApp Hotel Booking Platform")

        self.assertEqual(result["phi_status"], "unusable_response")
        self.assertIn('"domain": "travel"', result["phi_raw_response_preview"])

    def test_unusable_phi_response_keeps_attempt_level_preview_for_diagnostics(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.probe_json.return_value = {
            "http_status": 200,
            "parsed_json": {},
            "raw_content": "",
            "raw_response_preview": "",
            "attempts": [
                {
                    "raw_response_preview": '{"choices":[{"message":{"content":"```json',
                    "parsed_json": {},
                }
            ],
        }
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_task("WhatsApp Hotel Booking Platform")

        self.assertEqual(result["phi_status"], "unusable_response")
        self.assertIn('"choices"', result["phi_raw_response_preview"])

    def test_unusable_phi_response_keeps_non_dict_parsed_payload_for_diagnostics(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.probe_json.return_value = {
            "http_status": 200,
            "parsed_json": ["travel", "booking"],
            "raw_content": "",
            "raw_response_preview": "",
        }
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_task("WhatsApp Hotel Booking Platform")

        self.assertEqual(result["phi_status"], "unusable_response")
        self.assertIn("travel", result["phi_raw_response_preview"])

    def test_epic_stage_can_salvage_feature_titles_from_generated_work_items(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.probe_json.return_value = {
            "http_status": 200,
            "parsed_json": {
                "generated_work_items": [
                    {"draft_type": "Feature", "title": "Checkout Modernization"},
                    {"draft_type": "Feature", "title": "Payment Reliability"},
                ]
            },
            "raw_content": "",
            "raw_response_preview": "",
        }
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_epic_stage(
                "feature_generation",
                {"id": "1", "type": "Epic", "title": "Commerce Platform"},
                {"generated_features": []},
                {"effective_text": "Epic about checkout and payment."},
            )

        self.assertEqual(result["provider_used"], "azure_phi")
        self.assertEqual(result["parsed"]["features"], ["Checkout Modernization", "Payment Reliability"])

    def test_epic_stage_can_salvage_story_titles_from_rich_work_item_tree(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.probe_json.return_value = {
            "http_status": 200,
            "parsed_json": {
                "generated_work_items": [
                    {
                        "draft_type": "Feature",
                        "title": "Checkout Modernization",
                        "child_drafts": [
                            {"draft_type": "User Story", "title": "Review Order"},
                            {"draft_type": "User Story", "title": "Edit Cart"},
                        ],
                    }
                ]
            },
            "raw_content": "",
            "raw_response_preview": "",
        }
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_epic_stage(
                "story_generation",
                {"id": "1", "type": "Epic", "title": "Commerce Platform"},
                {"generated_features": [{"title": "Checkout Modernization"}]},
                {"effective_text": "Epic about checkout and payment."},
            )

        self.assertEqual(result["provider_used"], "azure_phi")
        self.assertEqual(result["parsed"]["stories"], ["Review Order", "Edit Cart"])


if __name__ == "__main__":
    unittest.main()
