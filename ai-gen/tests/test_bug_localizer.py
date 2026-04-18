"""Tests for deterministic bug hotspot localization."""

import unittest

from backend.repo_context.bug_localizer import detect_bug_surface, score_bug_hotspots


class BugLocalizerTests(unittest.TestCase):
    def test_detect_bug_surface(self) -> None:
        self.assertEqual(detect_bug_surface("fix login screen layout"), "ui")
        self.assertEqual(detect_bug_surface("fix auth endpoint bug"), "controller/api")
        self.assertEqual(detect_bug_surface("fix service logic"), "service")
        self.assertEqual(detect_bug_surface("fix session token issue"), "auth/session")
        self.assertIsNone(detect_bug_surface("fix odd behavior"))

    def test_hotspots_prefer_current_file_and_changed_files(self) -> None:
        hotspots = score_bug_hotspots(
            query="fix login ui bug",
            detected_flow="login",
            related_flows=["session"],
            file_index=[
                {"path": "ui/LoginScreen.kt", "flow": "login", "role": "ui"},
                {"path": "backend/SessionService.py", "flow": "session", "role": "service"},
            ],
            changed_files={"added": [], "modified": ["ui/LoginScreen.kt"], "deleted": []},
            current_file="ui/LoginScreen.kt",
            open_files=["backend/SessionService.py"],
        )

        self.assertEqual(hotspots[0]["file"], "ui/LoginScreen.kt")
        self.assertIn("matches current file", hotspots[0]["reasons"])
        self.assertIn("recently changed", hotspots[0]["reasons"])

    def test_ui_query_boosts_ui_files(self) -> None:
        hotspots = score_bug_hotspots(
            query="fix login screen bug",
            detected_flow="login",
            related_flows=[],
            file_index=[
                {"path": "ui/LoginScreen.kt", "flow": "login", "role": "ui"},
                {"path": "backend/AuthService.py", "flow": "login", "role": "service"},
            ],
            changed_files={"added": [], "modified": [], "deleted": []},
            current_file=None,
            open_files=[],
        )

        self.assertEqual(hotspots[0]["file"], "ui/LoginScreen.kt")

    def test_backend_query_boosts_service_and_controller_files(self) -> None:
        service_hotspots = score_bug_hotspots(
            query="fix auth service logic",
            detected_flow="login",
            related_flows=[],
            file_index=[
                {"path": "ui/LoginScreen.kt", "flow": "login", "role": "ui"},
                {"path": "backend/AuthService.py", "flow": "login", "role": "service"},
            ],
            changed_files={"added": [], "modified": [], "deleted": []},
            current_file=None,
            open_files=[],
        )
        controller_hotspots = score_bug_hotspots(
            query="fix auth endpoint",
            detected_flow="login",
            related_flows=[],
            file_index=[
                {"path": "backend/AuthController.py", "flow": "login", "role": "controller"},
                {"path": "backend/AuthService.py", "flow": "login", "role": "service"},
            ],
            changed_files={"added": [], "modified": [], "deleted": []},
            current_file=None,
            open_files=[],
        )

        self.assertEqual(service_hotspots[0]["file"], "backend/AuthService.py")
        self.assertEqual(controller_hotspots[0]["file"], "backend/AuthController.py")


if __name__ == "__main__":
    unittest.main()
