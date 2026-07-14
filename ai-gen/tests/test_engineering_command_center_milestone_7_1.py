from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore
from backend.workspace import WorkspaceService, build_workspace_router


class EngineeringCommandCenterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.platform = PlatformFoundation(root / "platform")
        self.service = WorkspaceService(JsonMapStore(root / "preferences.json"), platform=self.platform)

    def tearDown(self):
        self.temp.cleanup()

    def test_workspace_loads_with_shell_capabilities(self):
        workspace = self.service.get_workspace("operator-1", "contributor")
        self.assertEqual("Engineering Command Center", workspace["name"])
        self.assertEqual("Ready", workspace["status"]["state"])
        self.assertTrue(workspace["capabilities"]["globalSearch"])
        self.assertTrue(workspace["capabilities"]["commandPalette"])
        self.assertTrue(workspace["capabilities"]["keyboardNavigation"])
        self.assertTrue(workspace["capabilities"]["lazyLoading"])

    def test_navigation_contains_required_workspaces_in_order(self):
        items = self.service.get_navigation("admin")["items"]
        self.assertEqual([
            "overview", "planning", "repository", "execution", "approvals", "azure-devops",
            "agents", "activity", "health", "settings", "portfolio", "memory", "administration",
        ], [item["id"] for item in items])
        self.assertFalse(next(item for item in items if item["id"] == "portfolio")["enabled"])

    def test_navigation_is_role_aware(self):
        viewer = {item["id"] for item in self.service.get_navigation("viewer")["items"]}
        contributor = {item["id"] for item in self.service.get_navigation("contributor")["items"]}
        self.assertFalse({"repository", "settings", "administration"} & viewer)
        self.assertIn("azure-devops", viewer)
        self.assertNotIn("agents", viewer)
        self.assertIn("approvals", contributor)
        self.assertIn("agents", contributor)

    def test_theme_and_preferences_persist_per_user(self):
        value = self.service.update_preferences("admin-1", {"theme": "dark", "density": "compact", "sidebarCollapsed": True, "defaultWorkspace": "repository"}, "admin")
        self.assertEqual("dark", value["theme"])
        self.assertTrue(value["sidebarCollapsed"])
        self.assertEqual(value, self.service.get_preferences("admin-1"))
        self.assertEqual("system", self.service.get_preferences("other-user")["theme"])

    def test_role_prevents_unavailable_default_workspace(self):
        with self.assertRaisesRegex(ValueError, "not available"):
            self.service.update_preferences("viewer-1", {"defaultWorkspace": "administration"}, "viewer")

    def test_preference_update_is_audited(self):
        self.service.update_preferences("operator-1", {"theme": "light"}, "contributor")
        events = self.platform.audit.by_target("WorkspacePreferences", "operator-1")["events"]
        self.assertEqual("WorkspacePreferencesUpdated", events[0]["action"])

    def test_workspace_api_contract(self):
        app = FastAPI(); app.include_router(build_workspace_router(self.service)); client = TestClient(app)
        workspace = client.get("/workspace?userId=admin-1&role=admin")
        self.assertEqual(200, workspace.status_code)
        self.assertEqual(200, client.get("/workspace/navigation?role=viewer").status_code)
        updated = client.put("/workspace/preferences", json={"userId": "admin-1", "role": "admin", "theme": "dark", "defaultWorkspace": "repository"})
        self.assertEqual(200, updated.status_code)
        self.assertEqual("dark", client.get("/workspace/preferences?userId=admin-1").json()["theme"])

    def test_invalid_theme_returns_structured_error(self):
        app = FastAPI(); app.include_router(build_workspace_router(self.service)); client = TestClient(app)
        response = client.put("/workspace/preferences", json={"userId": "admin-1", "role": "admin", "theme": "neon"})
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_workspace_preferences", response.json()["error"]["code"])

    def test_shell_has_required_regions_and_keyboard_navigation(self):
        source = (Path(__file__).resolve().parents[1] / "azure-devops-extension/src/engineeringCommandCenterShell.tsx").read_text()
        for region in (
            "hei-command-header", "hei-command-sidebar", "hei-command-content",
            "hei-notification-area", "hei-command-statusbar", "hei-global-search",
            "hei-command-palette", "hei-workspace-switcher", "hei-user-menu",
        ):
            self.assertIn(region, source)
        self.assertIn("event.ctrlKey || event.metaKey", source)
        self.assertIn("event.key === '/'", source)
        self.assertIn("aria-current", source)

    def test_shell_has_responsive_and_theme_contracts(self):
        css = (Path(__file__).resolve().parents[1] / "azure-devops-extension/src/storyPlanner.css").read_text()
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn("@media (max-width: 620px)", css)
        self.assertIn(":root[data-hei-theme='dark']", css)
        self.assertIn("[data-hei-density='compact']", css)
        self.assertIn("focus-visible", css)


if __name__ == "__main__":
    unittest.main()
