"""Tests for compact final prompt packets."""

import unittest

from context_builder.builder import ContextBuilder
from context_builder.execution_packets import build_execution_packet, select_execution_files
from logic_store.store import LogicStore


class ExecutionPacketTests(unittest.TestCase):
    def test_select_execution_files_prioritizes_current_hotspots_and_limits(self) -> None:
        files = select_execution_files(
            current_file="ui/LoginScreen.kt",
            open_files=["ui/LoginViewModel.kt", "backend/AuthService.py", "extra/File.py"],
            likely_bug_hotspots=[
                {"file": "ui/LoginScreen.kt"},
                {"file": "backend/AuthController.py"},
                {"file": "backend/SessionService.py"},
            ],
            detected_flow="login",
            max_files=4,
        )

        self.assertEqual(
            files,
            [
                "ui/LoginScreen.kt",
                "backend/AuthController.py",
                "backend/SessionService.py",
                "ui/LoginViewModel.kt",
            ],
        )

    def test_execute_packet_is_compact_and_uses_no_replan_rules(self) -> None:
        packet = build_execution_packet(
            query="Fix login ui flow",
            selected_files=["ui/LoginScreen.kt"],
            detected_flow="login",
            related_flows=["session"],
            constraints=["Reuse existing token/session lifecycle logic."],
            likely_bug_hotspots=[
                {
                    "file": "ui/LoginScreen.kt",
                    "flow": "login",
                    "role": "ui",
                    "reasons": ["matches current file", "belongs to detected flow"],
                }
            ],
            refined_metadata={
                "variant": "phone_number",
                "surface": "ui_screen",
                "fields": ["phone_number"],
                "validations": ["required", "phone_format", "length_limit"],
                "first_pass_scope": ["login screen input", "phone validation", "submit action"],
                "unknowns": ["Is OTP required after phone submission?"],
            },
        )

        self.assertIn("# Task", packet)
        self.assertIn("# Likely Breakpoints", packet)
        self.assertIn("Do not repeat broad repo analysis unless necessary.", packet)
        self.assertIn("Avoid re-planning from scratch.", packet)
        self.assertIn("Variant:", packet)
        self.assertIn("phone_number", packet)
        self.assertIn("# Unknowns", packet)
        self.assertNotIn("## Plan", packet)

    def test_execute_packet_is_shorter_than_verbose_builder_prompt(self) -> None:
        builder = ContextBuilder(LogicStore())
        verbose = builder.build_prompt("Fix login ui flow", max_tokens=900)["optimized_prompt"]
        packet = build_execution_packet(
            query="Fix login ui flow",
            selected_files=["ui/LoginScreen.kt"],
            detected_flow="login",
            related_flows=["session"],
            constraints=["Reuse existing token/session lifecycle logic."],
            likely_bug_hotspots=[{"file": "ui/LoginScreen.kt", "flow": "login", "role": "ui", "reasons": ["matches current file"]}],
        )

        self.assertLess(len(packet.split()), len(verbose.split()))


if __name__ == "__main__":
    unittest.main()
