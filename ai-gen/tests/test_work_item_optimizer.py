"""Tests for Azure DevOps work item optimization."""

import os
import unittest
from unittest.mock import patch

from backend.work_item_optimizer import (
    infer_work_item_scope,
    infer_work_item_surface,
    optimize_work_item_request,
)

try:
    from backend.app import ContextRequest, build_context
except ModuleNotFoundError:
    ContextRequest = None
    build_context = None


class WorkItemOptimizerTests(unittest.TestCase):
    def test_regex_validation_maps_to_ui_validation(self) -> None:
        surface = infer_work_item_surface(
            "Fix login email regex issue with text limit cap for email and password",
            tags=["bug", "login"],
        )

        self.assertEqual(surface, "ui_validation")

    def test_login_email_password_scope_is_validation_focused(self) -> None:
        scope = infer_work_item_scope(
            "Fix login email regex issue with text limit cap for email and password",
            "ui_validation",
        )

        self.assertIn("login form input validation", scope)
        self.assertIn("email/password field validators", scope)

    def test_raw_bug_text_becomes_normalized_engineering_query(self) -> None:
        optimized = optimize_work_item_request(
            title="Fix the login email regex issue",
            description="should only accept @ symbol and have the text limit cap for email and password",
            tags=["bug", "login"],
            work_item_type="Bug",
        )

        self.assertEqual(optimized["technical_surface"], "ui_validation")
        self.assertEqual(
            optimized["normalized_query"],
            "Fix login form validation so email and password fields enforce valid format and length limits.",
        )
        self.assertIn("Check the UI/input validation layer", optimized["inferred_focus_rules"][0])

    def test_dashboard_story_maps_to_ui_screen(self) -> None:
        optimized = optimize_work_item_request(
            title="Add dashboard filter controls",
            description="Create filters on the dashboard page for status and owner",
            work_item_type="User Story",
        )

        self.assertEqual(optimized["technical_surface"], "ui_screen")
        self.assertIn("dashboard screen/page component", optimized["likely_scope"])

    def test_auth_api_task_maps_to_api_controller(self) -> None:
        optimized = optimize_work_item_request(
            title="Update auth API error response",
            description="Controller should return a generic response body for invalid credentials",
            work_item_type="Task",
        )

        self.assertEqual(optimized["technical_surface"], "api/controller")
        self.assertIn("login controller", optimized["likely_scope"])


class AzureContextIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        if ContextRequest is None or build_context is None:
            self.skipTest("FastAPI is not installed in this Python interpreter")

    def test_azure_devops_context_uses_normalized_task(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(
                ContextRequest(
                    query="Fix the login email regex issue. should only accept @ symbol and have the text limit cap for email and password",
                    source="azure_devops",
                    work_item={
                        "title": "Fix the login email regex issue",
                        "description": "should only accept @ symbol and have the text limit cap for email and password",
                        "acceptanceCriteria": "",
                        "tags": ["bug", "login"],
                        "type": "Bug",
                    },
                )
            )

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["work_item_optimized"], True)
        self.assertEqual(data["work_item_surface"], "ui_validation")
        self.assertIn("login form input validation", data["work_item_scope"])
        self.assertIn(
            "Fix login form validation so email and password fields enforce valid format and length limits.",
            data["optimized_prompt"],
        )
        self.assertIn("# Focus", data["optimized_prompt"])
        self.assertNotIn("should only accept @ symbol", data["optimized_prompt"])

    def test_ide_context_is_not_work_item_optimized(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(ContextRequest(query="Fix the login email regex issue"))

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["work_item_optimized"], False)
        self.assertIsNone(data["work_item_task_summary"])
        self.assertEqual(data["work_item_scope"], [])


if __name__ == "__main__":
    unittest.main()
