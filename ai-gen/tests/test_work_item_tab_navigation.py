from pathlib import Path
import unittest


class WorkItemTabNavigationTests(unittest.TestCase):
    def test_project_intelligence_tab_uses_top_cards_without_sidebar(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "azure-devops-extension/src/projectIntelligenceTab.tsx"
        ).read_text()

        shell_start = source.index("<EngineeringCommandCenterShell")
        shell_end = source.index(">", shell_start)
        shell_props = source[shell_start:shell_end]

        self.assertIn("hideSidebar", shell_props)
        self.assertIn("<WorkflowTabs", source[shell_end:])
        self.assertLess(
            source.index("<WorkflowTabs", shell_end),
            source.index("<StickyContextBar", shell_end),
        )

    def test_top_cards_cover_the_primary_work_item_lifecycle(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "azure-devops-extension/src/projectIntelligenceTab.tsx"
        ).read_text()

        for label in (
            "Command Center",
            "Planning",
            "Execution",
            "QA & Release",
            "Memory",
        ):
            self.assertIn(f"label: '{label}'", source)

        self.assertIn('aria-label="Project Intelligence workspace tabs"', source)
        self.assertIn("aria-current={activeTab === tab.id ? 'page' : undefined}", source)


if __name__ == "__main__":
    unittest.main()
