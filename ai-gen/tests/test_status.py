"""Tests for backend capabilities/status payload."""

import os
import unittest
from unittest.mock import MagicMock, patch

from backend.status import get_status


class StatusTests(unittest.TestCase):
    def test_status_payload_includes_availability_fields(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            status = get_status()

        self.assertEqual(status["backend_up"], True)
        self.assertEqual(status["codex_available"], True)
        self.assertEqual(status["local_enabled"], False)
        self.assertEqual(status["local_available"], False)
        self.assertIn("available_targets", status)
        self.assertIn("refiner", status)

    def test_local_enabled_missing_model_produces_warning(self) -> None:
        env = {
            "AI_GEN_LOCAL_ENABLED": "1",
            "AI_GEN_LOCAL_PROVIDER": "ollama",
        }
        with patch.dict(os.environ, env, clear=True), patch("shutil.which", return_value="/usr/bin/codex"), patch(
            "backend.status.is_ollama_reachable", return_value=True
        ):
            status = get_status()

        self.assertEqual(status["local_enabled"], True)
        self.assertIn("Local model name is not configured", status["warnings"])

    def test_ollama_unreachable_produces_warning(self) -> None:
        env = {
            "AI_GEN_LOCAL_ENABLED": "1",
            "AI_GEN_LOCAL_PROVIDER": "ollama",
            "AI_GEN_LOCAL_MODEL": "llama3.2",
            "AI_GEN_LOCAL_BASE_URL": "http://localhost:11434",
        }
        with patch.dict(os.environ, env, clear=True), patch("shutil.which", return_value="/usr/bin/codex"), patch(
            "backend.status.is_ollama_reachable", return_value=False
        ):
            status = get_status()

        self.assertEqual(status["local_available"], False)
        self.assertIn("Ollama is enabled but not reachable", status["warnings"])

    def test_codex_unavailable_produces_warning(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
            status = get_status()

        self.assertEqual(status["codex_available"], False)
        self.assertIn("Codex is not available on PATH", status["warnings"])

    def test_ollama_reachable_sets_local_available(self) -> None:
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        with patch.dict(
            os.environ,
            {
                "AI_GEN_LOCAL_ENABLED": "1",
                "AI_GEN_LOCAL_PROVIDER": "ollama",
                "AI_GEN_LOCAL_MODEL": "llama3.2",
            },
            clear=True,
        ), patch("shutil.which", return_value="/usr/bin/codex"), patch("urllib.request.urlopen", return_value=response):
            status = get_status()

        self.assertEqual(status["local_available"], True)
        self.assertEqual(status["local_base_url"], "http://localhost:11434")

    def test_refiner_enabled_but_not_configured_produces_warning(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
            },
            clear=True,
        ), patch("shutil.which", return_value="/usr/bin/codex"):
            status = get_status()

        self.assertEqual(status["refiner"]["enabled"], True)
        self.assertEqual(status["refiner"]["configured"], False)
        self.assertIn("Refiner is enabled but not fully configured", status["warnings"])


if __name__ == "__main__":
    unittest.main()
