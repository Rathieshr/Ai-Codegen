import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "azure-devops-extension"


class HEIExtensionIdentityTests(unittest.TestCase):
    def load_manifest(self, name: str) -> dict:
        return json.loads((EXTENSION / name).read_text(encoding="utf-8"))

    def test_hei_has_an_independent_install_identity(self) -> None:
        hei = self.load_manifest("azure-devops-extension.hei.json")
        legacy = self.load_manifest("azure-devops-extension.project-intelligence-preview.json")

        self.assertEqual(hei["name"], "HEI")
        self.assertEqual(hei["id"], "hei-engineering-platform")
        self.assertNotEqual(hei["id"], legacy["id"])
        self.assertNotEqual(hei["contributions"][0]["id"], legacy["contributions"][0]["id"])

    def test_hei_work_item_page_uses_hei_branding(self) -> None:
        hei = self.load_manifest("azure-devops-extension.hei.json")
        contribution = hei["contributions"][0]

        self.assertEqual(contribution["properties"]["name"], "HEI")
        self.assertEqual(contribution["properties"]["uri"], "projectIntelligenceTab.html")
        self.assertIn("projectIntelligenceTab.html", {item["path"] for item in hei["files"]})

    def test_legacy_extension_manifests_remain_available(self) -> None:
        work_item_tools = self.load_manifest("azure-devops-extension.json")
        project_intelligence = self.load_manifest("azure-devops-extension.project-intelligence-preview.json")

        self.assertEqual(work_item_tools["id"], "ai-gen-work-item-tools")
        self.assertEqual(project_intelligence["id"], "ai-gen-project-intelligence-preview")


if __name__ == "__main__":
    unittest.main()
