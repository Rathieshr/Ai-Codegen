import os
import unittest
from unittest.mock import patch

from backend.refinement.phi_provider import AzurePhiProvider


class PhiProviderTests(unittest.TestCase):
    def test_response_format_disabled_omits_response_format(self) -> None:
        captured = {}

        def fake_attempt(self, system_prompt, user_prompt, max_tokens, timeout_seconds, include_response_format, attempt_number):
            captured["include_response_format"] = include_response_format
            return {
                "attempt_number": attempt_number,
                "url_preview": "https://example.test/models/chat/completions?api-version=1",
                "method": "POST",
                "response_format_enabled": include_response_format,
                "http_status": 200,
                "status": "success",
                "elapsed_ms": 10,
                "timeout_seconds": timeout_seconds,
                "raw_response_preview": '{"status":"ok"}',
                "raw_content": '{"status":"ok"}',
                "parsed_json": {"status": "ok"},
                "parse_error": "",
                "max_tokens": max_tokens,
                "error_type": "",
                "error_message": "",
                "failure_reason": "",
                "failure_message": "",
            }

        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://phi.example/models",
                "AI_GEN_REFINER_API_KEY": "secret",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
                "AI_GEN_REFINER_RESPONSE_FORMAT_ENABLED": "0",
            },
            clear=False,
        ), patch.object(AzurePhiProvider, "_attempt_request", fake_attempt):
            provider = AzurePhiProvider()
            provider.probe_json("Return JSON", "{}", max_tokens=50, timeout_seconds=2)

        self.assertFalse(captured["include_response_format"])

    def test_retry_without_response_format_is_attempted(self) -> None:
        attempts = []

        def fake_attempt(self, system_prompt, user_prompt, max_tokens, timeout_seconds, include_response_format, attempt_number):
            attempts.append(include_response_format)
            if include_response_format:
                return {
                    "attempt_number": attempt_number,
                    "url_preview": "https://example.test/models/chat/completions?api-version=1",
                    "method": "POST",
                    "response_format_enabled": include_response_format,
                    "http_status": 405,
                    "status": "error",
                    "elapsed_ms": 2000,
                    "timeout_seconds": timeout_seconds,
                    "raw_response_preview": "",
                    "raw_content": "",
                    "parsed_json": {},
                    "parse_error": "HTTPError",
                    "max_tokens": max_tokens,
                    "error_type": "HTTPError",
                    "error_message": "405 Method Not Allowed",
                    "failure_reason": "http_405_wrong_method_or_path",
                    "failure_message": "Azure Phi endpoint rejected the HTTP method or path.",
                }
            return {
                "attempt_number": attempt_number,
                "url_preview": "https://example.test/models/chat/completions?api-version=1",
                "method": "POST",
                "response_format_enabled": include_response_format,
                "http_status": 200,
                "status": "success",
                "elapsed_ms": 200,
                "timeout_seconds": timeout_seconds,
                "raw_response_preview": '{"status":"ok"}',
                "raw_content": '{"status":"ok"}',
                "parsed_json": {"status": "ok"},
                "parse_error": "",
                "max_tokens": max_tokens,
                "error_type": "",
                "error_message": "",
                "failure_reason": "",
                "failure_message": "",
            }

        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://phi.example/models",
                "AI_GEN_REFINER_API_KEY": "secret",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
            },
            clear=False,
        ), patch.object(AzurePhiProvider, "_attempt_request", fake_attempt):
            provider = AzurePhiProvider()
            result = provider.probe_json("Return JSON", "{}", max_tokens=50, timeout_seconds=2)

        self.assertEqual(attempts, [True, False])
        self.assertTrue(result["json_mode_attempted"])
        self.assertTrue(result["json_mode_retry_without_response_format"])

    def test_url_builder_supports_root_models_and_chat_paths(self) -> None:
        cases = {
            "https://xxx.services.ai.azure.com": "https://xxx.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview",
            "https://xxx.services.ai.azure.com/models": "https://xxx.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview",
            "https://xxx.services.ai.azure.com/models/chat/completions": "https://xxx.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview",
        }
        for endpoint, expected in cases.items():
            with self.subTest(endpoint=endpoint), patch.dict(
                os.environ,
                {
                    "AI_GEN_REFINER_ENABLED": "1",
                    "AI_GEN_REFINER_PROVIDER": "azure_phi",
                    "AI_GEN_REFINER_ENDPOINT": endpoint,
                    "AI_GEN_REFINER_API_KEY": "secret",
                    "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
                    "AI_GEN_REFINER_API_VERSION": "2024-05-01-preview",
                },
                clear=False,
            ):
                provider = AzurePhiProvider()
                self.assertEqual(provider.final_url(), expected)
                self.assertNotIn("/models/models/", provider.final_url())

    def test_missing_api_key_shows_missing_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://phi.example/models",
                "AI_GEN_REFINER_API_KEY": "",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
            },
            clear=False,
        ):
            provider = AzurePhiProvider()
            result = provider.probe_json("Return JSON", "{}", max_tokens=50, timeout_seconds=2)

        self.assertEqual(result["failure_reason"], "missing_config")
        self.assertEqual(result["attempts"], [])

    def test_http_405_produces_actionable_message(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://phi.example/models",
                "AI_GEN_REFINER_API_KEY": "secret",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
            },
            clear=False,
        ):
            provider = AzurePhiProvider()
            result = provider._error_attempt(
                attempt_number=1,
                url=provider.final_url(),
                include_response_format=True,
                timeout_seconds=2,
                max_tokens=50,
                started=0.0,
                http_status=405,
                raw_preview="method not allowed",
                error_type="HTTPError",
                error_message="405 Method Not Allowed",
            )

        self.assertEqual(result["failure_reason"], "http_405_wrong_method_or_path")
        self.assertIn("method or path", result["failure_message"])

    def test_timeout_result_keeps_attempt_history(self) -> None:
        def fake_attempt(self, system_prompt, user_prompt, max_tokens, timeout_seconds, include_response_format, attempt_number):
            return {
                "attempt_number": attempt_number,
                "url_preview": "https://example.test/models/chat/completions?api-version=1",
                "method": "POST",
                "response_format_enabled": include_response_format,
                "http_status": None,
                "status": "timeout",
                "elapsed_ms": 2000,
                "timeout_seconds": timeout_seconds,
                "raw_response_preview": "",
                "raw_content": "",
                "parsed_json": {},
                "parse_error": "TimeoutError",
                "max_tokens": max_tokens,
                "error_type": "TimeoutError",
                "error_message": "timed out",
                "failure_reason": "provider_timeout",
                "failure_message": "Azure Phi request timed out before returning a response.",
            }

        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://phi.example/models",
                "AI_GEN_REFINER_API_KEY": "secret",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
            },
            clear=False,
        ), patch.object(AzurePhiProvider, "_attempt_request", fake_attempt):
            provider = AzurePhiProvider()
            result = provider.probe_json("Return JSON", "{}", max_tokens=50, timeout_seconds=2)

        self.assertEqual(result["failure_reason"], "provider_timeout")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["attempts"][0]["status"], "timeout")

    def test_debug_curl_hides_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://phi.example/models",
                "AI_GEN_REFINER_API_KEY": "super-secret",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
            },
            clear=False,
        ):
            provider = AzurePhiProvider()
            curl_command = provider.debug_curl("ping")

        self.assertIn("api-key: <REDACTED>", curl_command)
        self.assertNotIn("super-secret", curl_command)

    def test_safe_config_exposes_all_timeout_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://phi.example/models",
                "AI_GEN_REFINER_API_KEY": "super-secret",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
                "AI_GEN_REFINER_TIMEOUT_SECONDS": "60",
                "AI_GEN_REFINER_PING_TIMEOUT_SECONDS": "61",
                "AI_GEN_REFINER_DIAGNOSTIC_TIMEOUT_SECONDS": "75",
            },
            clear=False,
        ):
            provider = AzurePhiProvider()
            config = provider.safe_config()

        self.assertEqual(config["timeout_seconds"], 60)
        self.assertEqual(config["ping_timeout_seconds"], 61)
        self.assertEqual(config["diagnostic_timeout_seconds"], 75)


if __name__ == "__main__":
    unittest.main()
