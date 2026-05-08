"""Tests for task refiner provider integration."""

import unittest
from unittest.mock import patch

from backend.refinement.task_refiner import refine_task


class TaskRefinerTests(unittest.TestCase):
    def test_provider_disabled_returns_refinement_used_false(self) -> None:
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=None):
            result = refine_task("Add login screen with phone number")

        self.assertEqual(result["refinement_used"], False)

    def test_mocked_phi_response_returns_validated_refinement(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.refine_json.return_value = {
            "base_flow": "login",
            "variant": "phone_number",
            "surface": "ui_screen",
            "fields": ["phone_number"],
            "validations": ["required", "phone_format", "length_limit"],
            "first_pass_scope": ["login screen input", "phone validation", "submit action"],
            "unknowns": ["Is OTP required after phone submission?"],
            "confidence": "medium",
            "bad_key": "ignore me",
        }
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_task("Add a login screen with phone number", {"source": "azure_devops"})

        self.assertEqual(result["refinement_used"], True)
        self.assertEqual(result["refinement"]["variant"], "phone_number")
        self.assertEqual(result["refinement"]["fields"], ["phone_number"])
        self.assertNotIn("bad_key", result["refinement"])

    def test_malformed_phi_response_falls_back_safely(self) -> None:
        provider = unittest.mock.Mock()
        provider.is_enabled.return_value = True
        provider.refine_json.return_value = {"fields": ["src/LoginScreen.kt", "phone_number"]}
        with patch("backend.refinement.task_refiner.get_refinement_provider", return_value=provider):
            result = refine_task("Add login screen with phone number")

        self.assertEqual(result["refinement_used"], True)
        self.assertEqual(result["refinement"]["fields"], ["phone_number"])


if __name__ == "__main__":
    unittest.main()
