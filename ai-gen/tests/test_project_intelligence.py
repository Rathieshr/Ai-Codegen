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
                    "ui_guidelines": {"primary_color": "#0057D8", "accessibility_rules": ["WCAG AA"]},
                    "repository_sources": ["README.md"],
                }
            )

            loaded = service.get_profile()

        self.assertEqual(saved["project_description"], "Mobile commerce platform")
        self.assertEqual(loaded["applications"], ["Mobile App", "Backend"])
        self.assertEqual(loaded["ui_guidelines"]["primary_color"], "#0057D8")
        self.assertEqual(loaded["repository_sources"], ["README.md"])
        self.assertTrue(loaded["onboarding_completed"])

    def test_analyze_description_infers_preview_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            analyzed = service.analyze_description("iOS and Android mobile commerce app with backend APIs, checkout, payment and order analytics.")

        self.assertEqual(analyzed["knowledge_profile_preview"]["domain"], "E-commerce")
        self.assertIn("Mobile App", analyzed["applications"])
        self.assertIn("Backend", analyzed["applications"])
        self.assertIn("Analytics", analyzed["applications"])
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
                    "project_description": "Mobile commerce platform",
                    "applications": ["Mobile App", "Backend"],
                    "technology_stack": ["Kotlin", "FastAPI"],
                    "ui_guidelines": {"component_library": "Design System"},
                    "repository_sources": ["README.md"],
                },
            )

        self.assertIn("UI Prompt", prompts["ui_prompt"])
        self.assertIn("Dev Prompt", prompts["dev_prompt"])
        self.assertIn("QA Prompt", prompts["qa_prompt"])
        self.assertIn("Saved cards can be selected", prompts["qa_prompt"])


if __name__ == "__main__":
    unittest.main()
