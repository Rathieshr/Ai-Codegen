"""Tests for task refiner provider integration."""

import unittest
from unittest.mock import patch

from backend.refinement.task_refiner import refine_task


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


if __name__ == "__main__":
    unittest.main()
