"""Contract tests for Azure DevOps permission mapping in the HEI extension."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "azure-devops-extension" / "src"


class ADOPermissionPrecedenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.permissions = (EXTENSION / "permissions.ts").read_text()
        cls.project_tab = (EXTENSION / "projectIntelligenceTab.tsx").read_text()
        cls.host = (EXTENSION / "host" / "AzureDevOpsHostAdapter.ts").read_text()
        cls.hub = (EXTENSION / "heiApp.tsx").read_text()

    def test_one_resolver_is_used_by_hub_and_project_intelligence(self):
        self.assertIn("resolveAzureDevOpsPermission", self.host)
        self.assertIn("resolveAzureDevOpsPermission", self.project_tab)
        self.assertNotIn("AZURE_DEVOPS_PERMISSION_MAPPING_ENABLED", self.project_tab)
        self.assertNotIn("Permission Mapping Paused", self.project_tab)

    def test_role_precedence_is_admin_then_contributor_then_viewer(self):
        self.assertIn("const ROLE_PRECEDENCE: HEIRole[] = ['admin', 'contributor', 'viewer']", self.permissions)
        self.assertIn("admin_takes_precedence", self.permissions)
        self.assertIn("contributor_takes_precedence_over_viewer", self.permissions)

    def test_builtin_and_hei_groups_are_mapped(self):
        for group in (
            "hei administrators",
            "project administrators",
            "project collection administrators",
            "hei contributors",
            "contributors",
            "hei readers",
            "readers",
            "stakeholders",
        ):
            self.assertIn(f"'{group}'", self.permissions)

    def test_project_groups_are_scoped_to_the_current_project(self):
        self.assertIn("scopedToCurrentProject", self.permissions)
        self.assertIn("candidate.scope === normalize(projectName)", self.permissions)
        self.assertIn("projectName && isUnscoped && !isHeiGroup && !isCollectionAdmin", self.permissions)
        self.assertIn("ignored_groups", self.permissions)

    def test_lookup_failure_is_read_only_not_admin(self):
        self.assertIn("fail_closed_viewer", self.permissions)
        self.assertIn("Viewer access is applied", self.permissions)
        self.assertNotIn("organization_owner_fallback", self.permissions)
        self.assertNotIn("normalizeHostRole(route.role, 'admin')", self.host)

    def test_restricted_routes_are_hidden_and_guarded(self):
        self.assertIn("function canAccessPlannerTab", self.project_tab)
        self.assertIn("function canAccessRoute", self.hub)
        self.assertIn("if (route === 'settings') return role === 'admin'", self.hub)
        self.assertIn("route === 'planning' || route === 'execution'", self.hub)
        self.assertIn("function filterNavigationForRole", (EXTENSION / "engineeringCommandCenterShell.tsx").read_text())
        self.assertIn("tab === 'governance' || tab === 'agents' || tab === 'skills'", self.project_tab)

    def test_permission_diagnostics_explain_the_mapping(self):
        for field in ("matched_groups", "ignored_groups", "matched_roles", "selected_role", "precedence_rule"):
            self.assertIn(field, self.permissions)

    def test_installable_manifests_request_graph_membership_access(self):
        manifests = (
            ROOT / "azure-devops-extension" / "azure-devops-extension.json",
            ROOT / "azure-devops-extension" / "azure-devops-extension.hei.json",
            ROOT / "azure-devops-extension" / "azure-devops-extension.project-intelligence-preview.json",
        )
        for manifest in manifests:
            with self.subTest(manifest=manifest.name):
                self.assertIn('"vso.graph"', manifest.read_text())


if __name__ == '__main__':
    unittest.main()
