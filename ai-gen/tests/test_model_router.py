"""Tests for MVP execution target routing."""

import os
import unittest
from unittest.mock import patch

from backend.model_router import detect_execution_target, get_available_targets


class ModelRouterTests(unittest.TestCase):
    def test_explain_prefers_local_when_enabled(self) -> None:
        with patch.dict(os.environ, {"AI_GEN_LOCAL_ENABLED": "1"}, clear=True), patch("shutil.which", return_value=None):
            route = detect_execution_target("Explain login flow", intent="general")

        self.assertEqual(route["target"], "local")

    def test_explain_falls_back_to_preview_when_local_unavailable(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
            route = detect_execution_target("Explain login flow", intent="general")

        self.assertEqual(route["target"], "preview_only")

    def test_fix_prefers_codex_when_available(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            route = detect_execution_target("Fix login bug", intent="bug_fix")

        self.assertEqual(route["target"], "codex")

    def test_fix_falls_back_to_preview_when_codex_unavailable(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
            route = detect_execution_target("Fix login bug", intent="bug_fix")

        self.assertEqual(route["target"], "preview_only")

    def test_design_prefers_cloud_when_enabled(self) -> None:
        with patch.dict(os.environ, {"AI_GEN_CLOUD_ENABLED": "1"}, clear=True), patch("shutil.which", return_value=None):
            route = detect_execution_target("Design auth architecture", intent="general")

        self.assertEqual(route["target"], "cloud")

    def test_dashboard_design_prefers_codex_when_available(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            route = detect_execution_target("Design dashboard screen", intent="general")

        self.assertEqual(route["target"], "codex")
        self.assertEqual(route["reason"], "UI implementation task requires repo-facing execution")

    def test_auth_architecture_still_uses_architecture_routing(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            route = detect_execution_target("Design auth architecture", intent="general")

        self.assertEqual(route["target"], "preview_only")

    def test_forced_codex_unavailable_uses_preview(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
            route = detect_execution_target("Fix login bug", intent="bug_fix", routing_mode="codex")

        self.assertEqual(route["target"], "preview_only")

    def test_env_availability(self) -> None:
        env = {
            "AI_GEN_LOCAL_ENABLED": "1",
            "AI_GEN_CLOUD_ENABLED": "1",
            "AI_GEN_CODEX_ENABLED": "1",
        }
        with patch.dict(os.environ, env, clear=True), patch("shutil.which", return_value=None):
            available = get_available_targets()

        self.assertEqual(available, {"local": True, "cloud": True, "codex": True})


if __name__ == "__main__":
    unittest.main()
