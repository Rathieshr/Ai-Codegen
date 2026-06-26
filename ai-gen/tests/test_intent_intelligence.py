from __future__ import annotations

import unittest

from backend.intelligence.intent import IntentEngine, buildIntent, build_intent


class IntentIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = IntentEngine()

    def test_epic_dashboard_intent_extracts_business_goal_and_capability(self) -> None:
        intent = self.engine.build_intent(
            {
                "id": 109,
                "type": "Epic",
                "title": "Modernize Line Defender Operations Dashboard",
                "description": "Provide operations users with live fault event visibility, outage investigation, and asset health monitoring.",
                "tags": ["LineDefender", "Operations"],
            }
        )

        self.assertEqual(intent["workItemId"], 109)
        self.assertEqual(intent["workItemType"], "Epic")
        self.assertIn("Modernize Line Defender Operations Dashboard", intent["businessGoal"])
        self.assertIn(intent["primaryCapability"], ["Operational Awareness", "Investigation", "Dashboard"])
        self.assertIn("Operations User", intent["personas"])
        self.assertIn("Operations", intent["businessDomain"])
        self.assertIn("Fault Monitoring", intent["inferredModules"])
        self.assertIn("Dashboard Monitoring", intent["inferredFlows"])
        self.assertGreater(intent["confidence"], 0.5)
        self.assertTrue(intent["reasoning"])

    def test_story_extracts_explicit_user_goal_persona_actions_and_entities(self) -> None:
        intent = build_intent(
            {
                "type": "User Story",
                "title": "Open critical fault event details",
                "description": "As an Operations User, I want to review critical fault event details so that I can understand outage impact.",
                "acceptance_criteria": [
                    "Device ID, severity, timestamp, telemetry freshness, and asset health are visible.",
                    "Unauthorized users receive access denied.",
                ],
            }
        )

        self.assertEqual(intent["workItemType"], "Story")
        self.assertIn("Operations User", intent["personas"])
        self.assertIn("Operations User wants to review critical fault event details", intent["userGoal"])
        self.assertIn("Review", intent["actions"])
        self.assertIn("Fault", intent["entities"])
        self.assertIn("Telemetry", intent["technicalKeywords"])
        self.assertIn("Fault Monitoring", intent["inferredModules"])
        self.assertIn("Fault Review", intent["inferredFlows"])
        self.assertGreaterEqual(intent["confidence"], 0.7)

    def test_feature_authentication_intent_detects_security_and_token_refresh(self) -> None:
        intent = buildIntent(
            {
                "type": "Feature",
                "title": "Modernize customer authentication experience",
                "description": "Improve login, OTP validation, token refresh, session expiry handling, and role based access.",
            }
        )

        self.assertEqual(intent["workItemType"], "Feature")
        self.assertEqual(intent["primaryCapability"], "Authentication")
        self.assertIn("Authentication", intent["businessDomain"])
        self.assertIn("Authentication", intent["inferredModules"])
        self.assertIn("Token Refresh", intent["inferredFlows"])
        self.assertIn("Token", " ".join(intent["businessKeywords"] + intent["technicalKeywords"]))
        self.assertTrue(intent["reasoning"])

    def test_task_firmware_intent_detects_firmware_without_ai(self) -> None:
        intent = self.engine.build_intent(
            {
                "type": "Task",
                "title": "Add firmware rollout status mapping",
                "description": "Update backend API mapping for firmware version, rollout state, rollback reason, and device update channel.",
            }
        )

        self.assertEqual(intent["workItemType"], "Task")
        self.assertEqual(intent["primaryCapability"], "Firmware")
        self.assertIn("Firmware", intent["businessDomain"])
        self.assertIn("Firmware", intent["inferredModules"])
        self.assertIn("Firmware Rollout", intent["inferredFlows"])
        self.assertIn("API", intent["technicalKeywords"])
        self.assertGreater(intent["confidence"], 0.5)

    def test_telemetry_example_extracts_telemetry_keywords_modules_and_flows(self) -> None:
        intent = self.engine.build_intent(
            {
                "type": "Story",
                "title": "Review telemetry freshness for device health",
                "description": "Field Technician needs to monitor telemetry signal freshness and identify missing meter readings.",
                "area_path": "Utility Grid Management",
            }
        )

        self.assertIn("Field Technician", intent["personas"])
        self.assertEqual(intent["primaryCapability"], "Telemetry")
        self.assertIn("Telemetry", intent["businessDomain"])
        self.assertIn("Telemetry", intent["inferredModules"])
        self.assertIn("Telemetry Review", intent["inferredFlows"])
        self.assertIn("Monitor", intent["actions"])

    def test_outage_investigation_extracts_investigation_intent(self) -> None:
        intent = self.engine.build_intent(
            {
                "type": "Story",
                "title": "Start outage investigation from a fault event",
                "description": "Operations User can investigate outage impact from a critical fault event and correlate telemetry with device health.",
            }
        )

        self.assertEqual(intent["primaryCapability"], "Investigation")
        self.assertIn("Distribution", intent["businessDomain"])
        self.assertIn("Investigate", intent["actions"])
        self.assertIn("Investigation", intent["entities"])
        self.assertIn("Fault Monitoring", intent["inferredModules"])
        self.assertIn("Investigation", intent["inferredFlows"])


if __name__ == "__main__":
    unittest.main()
