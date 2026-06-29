from __future__ import annotations

import unittest

from backend.intelligence.capability import CapabilityEngine, buildCapabilityContext, build_capability_context
from backend.intelligence.intent import build_intent


PROFILE = {
    "applications": [
        {"name": "Operations Dashboard", "type": "Web Portal"},
        {"name": "Mobile Application", "type": "Mobile"},
        {"name": "Firmware Service", "type": "Firmware"},
        {"name": "Analytics Platform", "type": "Analytics"},
    ],
    "knowledge_registry": {
        "modules": [
            "Fault Monitoring",
            "Telemetry",
            "Device Health",
            "Asset Health",
            "Authentication",
            "Authorization",
            "Firmware",
            "Reporting",
            "Notification",
        ],
        "flows": [
            "Fault Review",
            "Investigation",
            "Telemetry Review",
            "Dashboard Monitoring",
            "Alert Review",
            "Authentication",
            "Token Refresh",
            "Firmware Rollout",
            "Export and Reporting",
        ],
        "dependencies": ["Operations owner review", "Telemetry owner alignment"],
    },
}


def names(items: list[dict]) -> list[str]:
    return [item["name"] for item in items]


class CapabilityIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CapabilityEngine()

    def capability_context(self, work_item: dict) -> dict:
        intent = build_intent(work_item)
        return self.engine.build_capability_context(intent, {"project_profile": PROFILE})

    def test_dashboard_epic_selects_operational_awareness_dashboard_and_reporting(self) -> None:
        context = self.capability_context(
            {
                "id": 109,
                "type": "Epic",
                "title": "Modernize operations dashboard",
                "description": "Provide a live dashboard view of operational status, production health, KPI visibility, and equipment status reporting.",
            }
        )

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertIn("Operational Awareness", selected)
        self.assertIn("Reliability Analytics", selected)
        self.assertIn("Telemetry", names(context["relevantModules"]))
        self.assertIn("Dashboard Monitoring", names(context["relevantFlows"]))
        self.assertGreater(context["confidence"], 0.5)
        self.assertTrue(context["capabilityReasoning"])

    def test_outage_investigation_selects_outage_fault_monitoring_and_telemetry(self) -> None:
        context = self.capability_context(
            {
                "type": "Story",
                "title": "Start outage investigation from fault event",
                "description": "Operations User can triage outage impact from a critical fault event and correlate telemetry with device health.",
            }
        )

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertIn("Outage Investigation", selected)
        self.assertIn("Fault Monitoring", selected)
        self.assertIn("Fault Monitoring", names(context["relevantModules"]))
        self.assertIn("Telemetry", names(context["relevantModules"]))
        self.assertIn("Investigation", names(context["relevantFlows"]))
        self.assertIn("Telemetry Review", names(context["relevantFlows"]))
        self.assertNotIn("Analytics Platform", names(context["relevantFlows"]))
        self.assertNotIn("Mobile Application", names(context["relevantFlows"]))

    def test_firmware_rollout_selects_firmware_management(self) -> None:
        context = self.capability_context(
            {
                "type": "Feature",
                "title": "Firmware rollout visibility",
                "description": "Show firmware version, upgrade state, rollback reason, compliance status, and device update progress.",
            }
        )

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertIn("Firmware Management", selected)
        self.assertIn("Firmware", names(context["relevantModules"]))
        self.assertIn("Firmware Rollout", names(context["relevantFlows"]))

    def test_login_token_story_selects_authentication_and_authorization(self) -> None:
        intent = build_intent(
            {
                "type": "Story",
                "title": "Handle secure login token expiry",
                "description": "As an Administrator, I want login, session expiry, token refresh, unauthorized access, and role checks handled clearly.",
            }
        )
        context = build_capability_context(intent, {"project_profile": PROFILE})

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertIn("Authentication", selected)
        self.assertIn("Authorization", selected)
        self.assertIn("Authentication", names(context["relevantModules"]))
        self.assertIn("Token Refresh", names(context["relevantFlows"]))

    def test_outage_investigation_rejects_firmware_management(self) -> None:
        context = self.capability_context(
            {
                "type": "Story",
                "title": "Review outage investigation timeline",
                "description": "Operations User investigates root cause and event timeline for fault event response.",
            }
        )

        rejected = {item["name"]: item["reason"] for item in context["rejectedCapabilities"]}
        self.assertIn("Firmware Management", rejected)
        self.assertIn("does not mention firmware", rejected["Firmware Management"])
        self.assertNotIn("Firmware", names(context["relevantModules"]))
        self.assertNotIn("Firmware Rollout", names(context["relevantFlows"]))

    def test_alerting_story_selects_alert_management_and_notification(self) -> None:
        intent = build_intent(
            {
                "type": "Story",
                "title": "Acknowledge critical operator alert",
                "description": "Operations User receives notification, acknowledges alarm escalation, and sees response audit history.",
            }
        )
        context = buildCapabilityContext(intent, {"project_profile": PROFILE})

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertIn("Alert Management", selected)
        self.assertIn("Audit History", selected)
        self.assertIn("Notification", names(context["relevantModules"]))
        self.assertIn("Alert Review", names(context["relevantFlows"]))

    def test_duplicate_operational_awareness_capabilities_are_deduplicated(self) -> None:
        context = self.capability_context(
            {
                "type": "Epic",
                "title": "Live operations dashboard monitoring",
                "description": "Improve live view dashboard monitoring for operational status and production health reporting.",
            }
        )

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertEqual(len(selected), len(set(selected)))
        self.assertTrue("Operational Awareness" in selected or "Dashboard Monitoring" in selected)

    def test_capability_context_includes_confidence_reasoning_and_context_sections(self) -> None:
        context = self.capability_context(
            {
                "type": "Task",
                "title": "Add fault event filter by severity",
                "description": "Create search and filtering behavior for fault event severity and telemetry freshness.",
            }
        )

        self.assertGreater(context["confidence"], 0.4)
        self.assertTrue(context["capabilityReasoning"])
        self.assertTrue(context["relevantModules"])
        self.assertTrue(context["relevantFlows"])
        self.assertIn("generatedAt", context)
        self.assertEqual(context["primaryCapability"]["type"], "capability")

    def test_critical_fault_detection_maps_to_fault_monitoring_capability(self) -> None:
        context = self.capability_context(
            {
                "type": "Epic",
                "title": "Critical Fault Detection",
                "description": "Operations users need to detect critical fault events, review severity, and open fault event details.",
            }
        )

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertIn("Fault Monitoring", selected)
        self.assertNotIn("Critical Fault Detection", selected)
        self.assertIn("Fault Monitoring", names(context["relevantModules"]))
        self.assertIn("Fault Event Review", names(context["relevantFlows"]))

    def test_live_operations_awareness_maps_to_operational_awareness(self) -> None:
        context = self.capability_context(
            {
                "type": "Feature",
                "title": "Live Operations Awareness",
                "description": "Operations users need live operations status and an operations monitoring view.",
            }
        )

        selected = [context["primaryCapability"]["name"], *names(context["secondaryCapabilities"])]
        self.assertIn("Operational Awareness", selected)
        self.assertNotIn("Fault Monitoring", selected)
        self.assertIn("Live Status Review", names(context["relevantFlows"]))

    def test_system_names_are_not_selected_as_flows(self) -> None:
        intent = build_intent(
            {
                "type": "Story",
                "title": "Review faults in Mobile Application and Analytics Platform",
                "description": "Operations users review critical fault events in the mobile application and analytics platform.",
            }
        )
        intent["inferredFlows"] = ["Mobile Application", "Analytics Platform", "Fault Event Review"]
        context = buildCapabilityContext(intent, {"project_profile": PROFILE})

        flows = names(context["relevantFlows"])
        self.assertIn("Fault Event Review", flows)
        self.assertNotIn("Mobile Application", flows)
        self.assertNotIn("Analytics Platform", flows)

    def test_application_selection_is_not_all_applications_by_default(self) -> None:
        context = self.capability_context(
            {
                "type": "Epic",
                "title": "Critical Fault Detection",
                "description": "Detect and review critical fault events from telemetry and device health.",
            }
        )

        applications = names(context["relevantApplications"])
        self.assertTrue(applications)
        self.assertLess(len(applications), len(PROFILE["applications"]))
        self.assertNotIn("Firmware Service", applications)


if __name__ == "__main__":
    unittest.main()
