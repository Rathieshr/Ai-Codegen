from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from backend.project_intelligence import ProjectIntelligenceService


class ProjectIntelligenceTests(unittest.TestCase):
    def test_save_and_load_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            saved = service.save_profile(
                {
                    "project_description": "Mobile commerce platform",
                    "applications": ["Mobile App", "Backend"],
                    "technology_stack": ["React", "FastAPI"],
                    "development_standards": {
                        "architecture_patterns": ["MVVM"],
                        "security_requirements": ["OAuth2"],
                        "testing_requirements": ["Code coverage >80%"],
                    },
                    "ui_guidelines": {"primary_color": "#0057D8", "accessibility_rules": ["WCAG AA"]},
                    "repository_sources": ["README.md"],
                }
            )

            loaded = service.get_profile()

        self.assertEqual(saved["project_description"], "Mobile commerce platform")
        self.assertEqual(loaded["applications"], [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend", "type": "Backend"}])
        self.assertEqual(loaded["technology_stack"]["frontend"], ["React"])
        self.assertEqual(loaded["technology_stack"]["backend"], ["FastAPI"])
        self.assertEqual(loaded["development_standards"]["architecture_patterns"], ["MVVM"])
        self.assertEqual(loaded["ui_guidelines"]["primary_color"], "#0057D8")
        self.assertEqual(loaded["repository_sources"], ["README.md"])
        self.assertEqual(loaded["knowledge_profile_preview"]["readiness"], "Advanced")
        self.assertTrue(loaded["onboarding_completed"])

    def test_analyze_description_infers_preview_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            analyzed = service.analyze_description("iOS and Android mobile commerce app with backend APIs, checkout, payment and order analytics.")

        self.assertEqual(analyzed["knowledge_profile_preview"]["domain"], "E-commerce")
        self.assertIn({"name": "Mobile App", "type": "Mobile"}, analyzed["applications"])
        self.assertIn({"name": "Backend", "type": "Backend"}, analyzed["applications"])
        self.assertIn({"name": "Analytics", "type": "Analytics"}, analyzed["applications"])
        self.assertEqual(analyzed["domain"], "E-commerce")
        self.assertEqual(analyzed["project_type"], "Multi-System Platform")
        self.assertEqual(analyzed["knowledge_profile_preview"]["repository_status"], "Repository README scan coming next.")

    def test_generate_story_prompts_returns_ui_dev_and_qa(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            prompts = service.generate_story_prompts(
                {
                    "title": "Checkout with saved card",
                    "description": "As a customer, I want to pay with a saved card.",
                    "acceptance_criteria": ["Saved cards can be selected during checkout."],
                },
                {
                    "project_name": "Commerce App",
                    "domain": "Retail",
                    "project_type": "Mobile Application",
                    "project_description": "Mobile commerce platform",
                    "applications": [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend", "type": "Backend"}],
                    "technology_stack": {"mobile": ["Kotlin"], "backend": ["FastAPI"]},
                    "development_standards": {"architecture_patterns": ["MVVM"], "security_requirements": ["OAuth2"]},
                    "ui_guidelines": {"component_library": "Design System"},
                    "repository_sources": ["README.md"],
                },
            )

        self.assertIn("UI Prompt", prompts["ui_prompt"])
        self.assertIn("Dev Prompt", prompts["dev_prompt"])
        self.assertIn("QA Prompt", prompts["qa_prompt"])
        self.assertIn("Saved cards can be selected", prompts["qa_prompt"])
        self.assertIn("Project Name: Commerce App", prompts["dev_prompt"])
        self.assertIn("Domain: Retail", prompts["dev_prompt"])
        self.assertIn("Development Standards: MVVM; OAuth2", prompts["dev_prompt"])


if __name__ == "__main__":
    unittest.main()
