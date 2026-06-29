from __future__ import annotations

import unittest

from backend.intelligence.epic_analysis import analyzeEpic
from backend.project_intelligence import ProjectIntelligenceService


PROFILE = {
    "project_name": "LineDefender",
    "domain": "Utility Grid Management",
    "project_description": "LineDefender provides operations dashboard visibility for fault events, telemetry, outages, and reliability analytics.",
    "applications": [
        {"name": "Operations Dashboard", "type": "Web Portal"},
        {"name": "Backend API", "type": "Backend"},
        {"name": "Analytics Platform", "type": "Analytics"},
    ],
    "knowledge_registry": {
        "modules": ["Fault Monitoring", "Telemetry", "Device Health", "Reporting", "Analytics", "Notifications"],
        "flows": ["Fault Event Review", "Fault Detail Review", "Outage Investigation", "Device Health Review", "Reliability Trend Review", "Operations Monitoring"],
        "components": ["FaultMonitoringService", "FaultController", "FaultRepository", "FaultEvent", "TelemetryService"],
        "source_files": ["backend/faults/service.py", "backend/faults/controller.py", "backend/telemetry/service.py"],
        "dependencies": ["Telemetry owner alignment"],
    },
}


class EpicAnalysisIntelligenceTests(unittest.TestCase):
    def test_dashboard_epic_extracts_operational_visibility_problem(self) -> None:
        analysis = analyzeEpic(
            {
                "id": 109,
                "type": "Epic",
                "title": "Modernize LineDefender Operations Dashboard",
                "description": "Provide live status, critical fault visibility, alert response, outage investigation, and reliability trends.",
            },
            PROFILE,
        )

        problems = " ".join(analysis["businessProblems"])
        self.assertIn("unified operational visibility", problems)
        self.assertGreaterEqual(analysis["confidence"], 0.7)
        self.assertGreaterEqual(analysis["diagnostics"]["capability_count"], 4)

    def test_fault_monitoring_is_capability_not_feature(self) -> None:
        analysis = analyzeEpic(
            {"title": "Real-Time Fault Event Monitoring", "description": "Detect and review critical fault events."},
            PROFILE,
        )

        capability_names = [item["name"] for item in analysis["requiredCapabilities"]]
        self.assertIn("Fault Monitoring", capability_names)
        self.assertNotIn("Critical Fault Detection", capability_names)

    def test_firmware_update_is_out_of_scope_when_not_in_epic(self) -> None:
        analysis = analyzeEpic(
            {"title": "Modernize Operations Dashboard", "description": "Improve dashboard, fault review, alert response, and reliability trends."},
            PROFILE,
        )

        boundary = analysis["planningBoundary"]
        self.assertIn("Firmware Management", boundary["outOfScope"])

    def test_capability_relationships_priorities_and_evidence_are_generated(self) -> None:
        analysis = analyzeEpic(
            {"title": "Operations Dashboard Fault Monitoring", "description": "Improve fault events, alerts, outage investigation, and reliability analytics."},
            PROFILE,
        )

        relationships = {(item["source"], item["relationship"], item["target"]) for item in analysis["capabilityRelationships"]}
        priorities = {item["name"]: item["priority"] for item in analysis["capabilityPriority"]}
        fault = next(item for item in analysis["requiredCapabilities"] if item["name"] == "Fault Monitoring")

        self.assertIn(("Fault Monitoring", "supports", "Outage Investigation"), relationships)
        self.assertEqual(priorities["Fault Monitoring"], "Critical")
        self.assertTrue(fault["repositoryEvidence"])

    def test_refine_epic_uses_epic_analysis_and_generates_distinct_features(self) -> None:
        refined = ProjectIntelligenceService().refine_epic(
            {
                "id": 109,
                "type": "Epic",
                "title": "Modernize LineDefender Operations Dashboard",
                "description": "Provide live status, critical fault visibility, alert response, outage investigation, and reliability trends.",
            },
            PROFILE,
            options={"force_provider": "deterministic_fallback"},
        )

        titles = [feature["title"] for feature in refined["recommended_features"]]
        capabilities = [feature["capability"] for feature in refined["recommended_features"]]

        self.assertIn("epic_analysis", refined)
        self.assertEqual(refined["capability_diagnostics"]["feature_generation_mode"], "one_capability_at_a_time")
        self.assertIn("Critical Fault Detection", titles)
        self.assertIn("Fault Monitoring", capabilities)
        self.assertEqual(len(capabilities), len(set(capabilities)))
        self.assertNotIn("Firmware Rollout Visibility", titles)
        self.assertIn("Firmware Management", refined["planning_boundary"]["outOfScope"])


if __name__ == "__main__":
    unittest.main()
