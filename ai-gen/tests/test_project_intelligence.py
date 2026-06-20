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

    def test_analyze_readme_updates_knowledge_registry_and_prompts(self) -> None:
        readme = """
# Smart Meter Platform
Smart meter operations platform for mobile field work, backend APIs, and analytics.

## Modules
- Meter Inventory
- Outage Alerts
- Billing Sync

## Flows
- Meter onboarding
- Field inspection
- Consumption analytics

## Architecture
- Mobile app uses MVVM.
- Backend APIs use repository pattern.
- Events publish meter readings to analytics.
"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            profile = service.analyze_readme(
                readme,
                {"id": "repo-1", "name": "meter-platform", "branch": "main", "readme_path": "/README.md"},
                {"project_description": "Smart meter project", "technology_stack": {"mobile": ["Kotlin"], "backend": ["FastAPI"]}},
            )
            prompts = service.generate_story_prompts({"title": "Meter onboarding"}, profile)

        self.assertEqual(profile["repository_connection"]["status"], "README analyzed")
        self.assertIn("Meter Inventory", profile["knowledge_registry"]["modules"])
        self.assertIn("Meter onboarding", profile["knowledge_registry"]["flows"])
        self.assertIn("Detected Modules: Meter Inventory", prompts["dev_prompt"])
        self.assertIn("Detected Flows: Meter onboarding", prompts["dev_prompt"])

    def test_project_aware_epic_refinement_avoids_generic_slices(self) -> None:
        profile = {
            "project_name": "LineDefender Smart Monitoring Platform",
            "domain": "Utility Grid Management",
            "project_type": "Multi-System Platform",
            "project_description": "Monitor line devices, telemetry, firmware upgrades and fault events.",
            "applications": [{"name": "Operations Portal", "type": "Web Portal"}, {"name": "Device API", "type": "Backend"}],
            "technology_stack": {"backend": ["FastAPI"], "frontend": ["React"]},
            "knowledge_registry": {
                "modules": ["Telemetry", "Firmware Update", "Fault Event"],
                "flows": ["Device monitoring", "Fault triage", "Firmware rollout"],
            },
            "readme_analysis": {"architecture_notes": ["Backend APIs use repository pattern."]},
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            refined = service.refine_epic({"title": "Improve Device Monitoring", "description": "Improve telemetry, fault and firmware visibility."}, profile)

        feature_titles = [feature["title"] for feature in refined["recommended_features"]]
        self.assertIn("Fault Event Monitoring", feature_titles)
        self.assertIn("Telemetry Health Dashboard", feature_titles)
        self.assertIn("Firmware Upgrade Visibility", feature_titles)
        self.assertFalse(any("Slice" in title or title in {"Story 1", "Story 2"} for title in feature_titles))

    def test_story_refinement_uses_modules_flows_and_considerations(self) -> None:
        profile = {
            "project_name": "LineDefender Smart Monitoring Platform",
            "domain": "Utility Grid Management",
            "project_description": "Device monitoring platform.",
            "applications": [{"name": "Operations Portal", "type": "Web Portal"}],
            "technology_stack": {"backend": ["FastAPI"], "frontend": ["React"]},
            "development_standards": {"testing_requirements": ["Unit tests required"]},
            "ui_guidelines": {"component_library": "LineDefender UI", "accessibility_rules": ["WCAG AA"]},
            "knowledge_registry": {
                "modules": ["Telemetry", "Firmware Update", "Fault Event"],
                "flows": ["Device monitoring", "Fault triage"],
            },
            "readme_analysis": {"architecture_notes": ["Events publish readings to analytics."]},
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            refined = service.refine_story({"title": "View device telemetry health state"}, profile)

        self.assertIn("Operations Portal", refined["affected_applications"])
        self.assertIn("Telemetry", refined["affected_modules"])
        self.assertIn("Device monitoring", refined["affected_flows"])
        self.assertIn("LineDefender UI", " ".join(refined["ui_considerations"]))
        self.assertIn("Unit tests required", refined["qa_considerations"])

    def test_story_impact_identifies_otp_dependencies(self) -> None:
        profile = {
            "project_name": "Customer Access Platform",
            "domain": "Retail",
            "project_type": "Mobile Application",
            "project_description": "Customer mobile app with backend authentication APIs.",
            "applications": [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend API", "type": "Backend"}],
            "knowledge_registry": {
                "modules": ["Authentication", "Customer Profile"],
                "flows": ["Login", "Token Refresh"],
                "components": ["OTP Entry Screen"],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            impact = service.analyze_story_impact({"title": "Add OTP Login", "description": "Users verify login with SMS OTP and token refresh."}, profile)

        self.assertIn("Mobile App", impact["affected_applications"])
        self.assertIn("Backend API", impact["affected_applications"])
        self.assertIn("Authentication", impact["affected_modules"])
        self.assertIn("Login", impact["affected_flows"])
        self.assertIn("Auth Service", impact["dependencies"])
        self.assertIn("SMS Provider", impact["dependencies"])
        self.assertIn("Session invalidation", impact["risks"])

    def test_story_impact_uses_linedefender_repository_knowledge(self) -> None:
        profile = {
            "project_name": "LineDefender Smart Monitoring Platform",
            "domain": "Utility Grid Management",
            "project_type": "Multi-System Platform",
            "project_description": "Line device monitoring with telemetry, fault events, and field operations.",
            "applications": [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend API", "type": "Backend"}],
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry", "Event Repository"],
                "flows": ["Fault Event Review", "Telemetry Review"],
                "components": ["Fault Detail Screen", "Event Timeline"],
            },
            "readme_analysis": {"architecture_notes": ["Events publish telemetry to the operations API."]},
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            impact = service.analyze_story_impact({"title": "Display Fault Event Details", "description": "Show large fault history with connectivity-aware telemetry details."}, profile)

        self.assertIn("Mobile App", impact["affected_applications"])
        self.assertIn("Backend API", impact["affected_applications"])
        self.assertIn("Fault Monitoring", impact["affected_modules"])
        self.assertIn("Telemetry", impact["affected_modules"])
        self.assertIn("Fault Event Review", impact["affected_flows"])
        self.assertIn("Event Repository", impact["dependencies"])
        self.assertIn("Telemetry Service", impact["dependencies"])
        self.assertIn("Large event history performance", impact["risks"])
        self.assertIn("Connectivity issues", impact["risks"])

    def test_feature_and_epic_impact_return_domain_specific_dependencies(self) -> None:
        profile = {
            "project_name": "LineDefender Smart Monitoring Platform",
            "domain": "Utility Grid Management",
            "project_description": "Monitor telemetry, faults, and firmware rollout.",
            "applications": [{"name": "Operations Portal", "type": "Web Portal"}, {"name": "Device API", "type": "Backend"}],
            "knowledge_registry": {
                "modules": ["Telemetry", "Firmware Update", "Fault Monitoring"],
                "flows": ["Device monitoring", "Fault Event Review", "Firmware Rollout"],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            feature_impact = service.analyze_feature_impact({"title": "Fault Event Monitoring"}, profile)
            epic_impact = service.analyze_epic_impact({"title": "Improve Device Monitoring"}, profile)

        self.assertIn("Fault Monitoring", feature_impact["affected_modules"])
        self.assertIn("Fault Event Review", feature_impact["affected_flows"])
        self.assertIn("Coordinate across Backend, Web Portal teams", feature_impact["cross_team_dependencies"])
        self.assertIn("Release planning and stakeholder communication", epic_impact["program_dependencies"])
        self.assertIn("Roll out by device cohort", epic_impact["recommended_rollout_strategy"])

    def test_story_prompts_include_impact_context(self) -> None:
        profile = {
            "project_name": "LineDefender Smart Monitoring Platform",
            "domain": "Utility Grid Management",
            "project_description": "Line device monitoring with fault events.",
            "applications": [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend API", "type": "Backend"}],
            "technology_stack": {"mobile": ["Kotlin"], "backend": ["FastAPI"]},
            "development_standards": {"testing_requirements": ["Regression tests required"]},
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry"],
                "flows": ["Fault Event Review"],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            prompts = service.generate_story_prompts({"title": "Display Fault Event Details", "acceptance_criteria": ["Fault details are visible."]}, profile)

        self.assertIn("Affected Applications: Mobile App, Backend API", prompts["ui_prompt"])
        self.assertIn("Fault Event Review", prompts["ui_prompt"])
        self.assertIn("Fault Monitoring", prompts["dev_prompt"])
        self.assertIn("Telemetry", prompts["dev_prompt"])
        self.assertIn("Event Repository", prompts["dev_prompt"])
        self.assertIn("Large event history performance", prompts["qa_prompt"])
        self.assertIn("Fault Monitoring API", prompts["qa_prompt"])

    def test_execution_context_builder_uses_project_and_impact_intelligence(self) -> None:
        profile = {
            "project_name": "LineDefender Mobile Platform",
            "domain": "Utility Grid Management",
            "project_type": "Multi-System Platform",
            "project_description": "Hubbell field operations platform for fault event review.",
            "repository_connection": {"status": "README analyzed"},
            "applications": [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend API", "type": "Backend"}],
            "technology_stack": {"mobile": ["MAUI"], "backend": [".NET"]},
            "development_standards": {
                "architecture_patterns": ["MVVM", "Repository Pattern"],
                "testing_requirements": ["Unit Tests Required"],
            },
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry", "Event Repository"],
                "flows": ["Fault Event Review"],
                "components": ["Fault Detail Screen"],
            },
            "readme_analysis": {"architecture_notes": ["Mobile app uses MVVM.", "Backend APIs use Repository Pattern."]},
        }
        story = {
            "title": "Display Fault Event Details",
            "description": "As a field operator, I want to display fault event details.",
            "acceptance_criteria": ["Fault event details are visible from the event list."],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            context = service.build_execution_context(story, profile)

        self.assertIn("Mobile App", context["affected_applications"])
        self.assertIn("Backend API", context["affected_applications"])
        self.assertIn("Fault Monitoring", context["affected_modules"])
        self.assertIn("Telemetry", context["affected_modules"])
        self.assertIn("Fault Event Review", context["affected_flows"])
        self.assertIn("Telemetry Service", context["dependencies"])
        self.assertIn("Event Repository", context["dependencies"])
        self.assertEqual(context["technology_stack"]["mobile"], ["MAUI"])
        self.assertEqual(context["technology_stack"]["backend"], [".NET"])
        self.assertIn("MVVM", context["development_standards"]["architecture_patterns"])
        self.assertIn("Execution Ready", context["execution_readiness"])

    def test_prompt_builders_and_copilot_context_are_project_aware(self) -> None:
        profile = {
            "project_name": "LineDefender Mobile Platform",
            "domain": "Utility Grid Management",
            "project_type": "Multi-System Platform",
            "project_description": "Hubbell field operations platform for fault event review.",
            "repository_connection": {"status": "README analyzed"},
            "applications": [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend API", "type": "Backend"}],
            "technology_stack": {"mobile": ["MAUI"], "backend": [".NET"]},
            "ui_guidelines": {
                "primary_color": "#004B8D",
                "typography": "Segoe UI",
                "component_library": "Hubbell Mobile UI",
                "accessibility_rules": ["WCAG AA"],
            },
            "development_standards": {
                "architecture_patterns": ["MVVM", "Repository Pattern"],
                "testing_requirements": ["Unit Tests Required"],
            },
            "knowledge_registry": {
                "modules": ["Fault Monitoring", "Telemetry"],
                "flows": ["Fault Event Review"],
            },
            "readme_analysis": {"architecture_notes": ["Mobile app uses MVVM.", "Backend APIs use Repository Pattern."]},
        }
        story = {"title": "Display Fault Event Details", "acceptance_criteria": ["Fault details include timestamp and severity."]}
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            service = ProjectIntelligenceService()
            dev_prompt = service.build_dev_prompt(story, profile)["prompt"]
            ui_prompt = service.build_ui_prompt(story, profile)["prompt"]
            qa_prompt = service.build_qa_prompt(story, profile)["prompt"]
            copilot_context = service.build_copilot_context(story, profile)["context"]

        self.assertIn("Technology Stack: mobile: MAUI; backend: .NET", dev_prompt)
        self.assertIn("Coding Standards: MVVM; Repository Pattern; Unit Tests Required", dev_prompt)
        self.assertIn("Architecture Rules: Mobile app uses MVVM., Backend APIs use Repository Pattern.", dev_prompt)
        self.assertIn("Component Library: Hubbell Mobile UI", ui_prompt)
        self.assertIn("Affected User Flows:", ui_prompt)
        self.assertIn("Fault Event Review", ui_prompt)
        self.assertIn("Risks: Large event history performance", qa_prompt)
        self.assertIn("Regression Areas:", qa_prompt)
        self.assertIn("Fault Event Review", qa_prompt)
        self.assertIn("Fault Monitoring", qa_prompt)
        self.assertIn("Project: LineDefender Mobile Platform", copilot_context)
        self.assertIn("Fault Monitoring", copilot_context)
        self.assertIn("Telemetry", copilot_context)
        self.assertIn("Repository Pattern", copilot_context)


if __name__ == "__main__":
    unittest.main()
