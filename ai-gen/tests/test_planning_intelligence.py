from __future__ import annotations

import unittest

from backend.intelligence.intent import build_intent
from backend.intelligence.capability import buildCapabilityContext
from backend.intelligence.planning import PlanningEngine, buildPlanningContext, build_planning_context


PROFILE = {
    "applications": [
        {"name": "Operations Dashboard", "type": "Web Portal"},
        {"name": "Mobile Application", "type": "Mobile"},
        {"name": "Firmware Service", "type": "Firmware"},
        {"name": "Analytics Platform", "type": "Analytics"},
        {"name": "Auth Console", "type": "Authentication"},
    ],
    "knowledge_registry": {
        "modules": [
            "Dashboard",
            "Fault Monitoring",
            "Telemetry",
            "Device Health",
            "Authentication",
            "Authorization",
            "Firmware",
            "Reporting",
            "Notification",
            "Outage Timeline",
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
        "dependencies": ["Operations owner review", "Telemetry owner alignment", "Auth owner alignment"],
        "standards": ["Acceptance criteria traceability", "Repository-ranked files only", "No broad context leakage"],
    },
}

REPOSITORY = {
    "modules": [
        {"name": "Dashboard", "path": "azure-devops-extension/src/projectIntelligenceTab.tsx", "keywords": ["dashboard", "monitoring"]},
        {"name": "Fault Monitoring", "path": "backend/repo_context/bug_localizer.py", "keywords": ["fault", "outage", "investigation"]},
        {"name": "Telemetry", "path": "backend/repo_context/cross_flow.py", "keywords": ["telemetry", "signal"]},
        {"name": "Authentication", "path": "backend/auth/middleware.py", "keywords": ["login", "token", "session"]},
        {"name": "Firmware", "path": "backend/firmware/service.py", "keywords": ["firmware", "rollout"]},
    ],
    "flows": ["Dashboard Monitoring", "Investigation", "Fault Review", "Token Refresh", "Firmware Rollout"],
    "dependencies": ["Telemetry owner alignment", "Auth owner alignment"],
    "rankedFiles": [
        {"path": "backend/repo_context/bug_localizer.py", "score": 0.91, "keywords": ["fault", "outage"]},
        {"path": "backend/auth/middleware.py", "score": 0.87, "keywords": ["token", "session"]},
    ],
}


def names(items: list[dict]) -> list[str]:
    return [item["name"] for item in items]


def make_context(work_item: dict, parent: dict | None = None, existing_children: list[dict] | None = None) -> dict:
    intent = build_intent(work_item)
    capability = buildCapabilityContext(intent, {"project_profile": PROFILE})
    return buildPlanningContext(
        work_item,
        parent or work_item,
        {
            "intentModel": intent,
            "capabilityContext": capability,
            "projectProfile": PROFILE,
            "repositorySnapshot": REPOSITORY,
            "knowledgeRegistry": PROFILE["knowledge_registry"],
            "existingChildren": existing_children or [],
        },
    )


class PlanningIntelligenceTests(unittest.TestCase):
    def test_epic_dashboard_context_selects_dashboard_monitoring_alerting_analytics_capabilities(self) -> None:
        epic = {
            "id": 200,
            "type": "Epic",
            "title": "Modernize operations dashboard",
            "description": "Provide a live dashboard for monitoring operational status, critical alerts, KPI analytics, and equipment health.",
        }

        context = make_context(epic)

        selected = names(context["selectedCapabilities"])
        self.assertIn("Operational Awareness", selected)
        self.assertIn("Alert Management", selected)
        self.assertIn("Reliability Analytics", selected)
        self.assertIn("Dashboard", names(context["selectedModules"]))
        self.assertIn("Dashboard Monitoring", names(context["selectedFlows"]))

    def test_feature_outage_investigation_context_selects_outage_investigation_only(self) -> None:
        epic = {"id": 200, "type": "Epic", "title": "Operations dashboard", "description": "Dashboard monitoring and outage investigation."}
        feature = {
            "id": 201,
            "type": "Feature",
            "title": "Outage investigation workspace",
            "description": "Enable operators to investigate outage root cause from fault events and telemetry timeline.",
            "acceptanceCriteria": ["Operators can start investigation from a critical fault event."],
        }

        context = make_context(feature, epic)

        selected = names(context["selectedCapabilities"])
        self.assertIn("Outage Investigation", selected)
        self.assertIn("Fault Monitoring", selected)
        self.assertNotIn("Firmware Management", selected)
        self.assertIn("Investigation", names(context["selectedFlows"]))

    def test_story_start_investigation_context_selects_technical_areas_from_acceptance_criteria(self) -> None:
        feature = {"id": 201, "type": "Feature", "title": "Outage investigation workspace", "description": "Investigate outage root cause from fault event telemetry."}
        story = {
            "id": 202,
            "type": "Story",
            "title": "Start investigation from fault event",
            "description": "As an operator, I can start an investigation from a critical fault event.",
            "acceptanceCriteria": [
                "Given a critical fault event, when I start investigation, then the outage timeline opens.",
                "Telemetry and device health context are shown for the selected fault event.",
            ],
        }

        context = make_context(story, feature)

        self.assertIn("Fault Monitoring", names(context["selectedModules"]))
        self.assertIn("Telemetry", names(context["selectedModules"]))
        self.assertIn("Investigation", names(context["selectedFlows"]))
        self.assertTrue(any("acceptance" in ref["reason"].lower() for ref in context["selectedModules"]))

    def test_firmware_is_rejected_when_not_present_in_parent_intent(self) -> None:
        context = make_context({"id": 203, "type": "Feature", "title": "Outage timeline", "description": "Investigate fault outage timeline and telemetry."})

        rejected = {item["name"]: item["reason"] for item in context["rejectedContext"]}
        self.assertIn("Firmware Management", rejected)
        self.assertIn("does not mention firmware", rejected["Firmware Management"])
        self.assertNotIn("Firmware", names(context["selectedModules"]))

    def test_token_refresh_is_rejected_unless_auth_session_intent_exists(self) -> None:
        context = make_context({"id": 204, "type": "Story", "title": "Outage refresh", "description": "Refresh outage telemetry in the dashboard."})
        rejected = {item["name"]: item["reason"] for item in context["rejectedContext"]}
        self.assertIn("Token Refresh", rejected)
        self.assertNotIn("Token Refresh", names(context["selectedFlows"]))

        auth_context = make_context({"id": 205, "type": "Story", "title": "Refresh expired login token", "description": "Refresh token when login session expires."})
        self.assertIn("Token Refresh", names(auth_context["selectedFlows"]))

    def test_duplicate_feature_detection_works(self) -> None:
        epic = {"id": 200, "type": "Epic", "title": "Operations dashboard", "description": "Live operations dashboard monitoring and critical fault visibility."}
        feature = {"id": 206, "type": "Feature", "title": "Critical fault detection", "description": "Detect critical fault conditions on live operations dashboard."}

        context = make_context(
            feature,
            epic,
            existing_children=[{"id": 900, "type": "Feature", "title": "Live Operations Awareness", "description": "Detect critical faults and surface live dashboard status."}],
        )

        self.assertTrue(context["risks"])
        self.assertTrue(any("duplicate" in risk.lower() for risk in context["risks"]))
        self.assertTrue(context["diagnostics"]["duplicateRisks"])

    def test_planning_context_includes_lineage(self) -> None:
        parent = {"id": 300, "type": "Epic", "title": "Operations dashboard", "description": "Dashboard monitoring."}
        child = {"id": 301, "type": "Feature", "title": "Dashboard monitoring", "description": "Monitor status."}

        context = make_context(child, parent)

        self.assertEqual(context["lineage"]["derivedFromId"], 300)
        self.assertEqual(context["lineage"]["derivedFromType"], "Epic")
        self.assertIn("Epic → Feature", context["lineage"]["derivationRule"])

    def test_planning_context_includes_generation_role(self) -> None:
        context = make_context({"id": 400, "type": "Story", "title": "Start investigation", "description": "Investigate fault event."})

        self.assertEqual(context["generationRole"], "ScrumMaster")
        self.assertTrue(context["generationObjective"])

    def test_planning_context_includes_rejected_context(self) -> None:
        context = make_context({"id": 401, "type": "Story", "title": "Dashboard fault alert", "description": "Show fault alert on dashboard."})

        self.assertTrue(context["rejectedContext"])
        self.assertIn("rejectedContext", context["diagnostics"])

    def test_planning_context_token_estimate_is_populated(self) -> None:
        context = build_planning_context({"id": 500, "type": "Task", "title": "Add fault filter", "description": "Filter fault events by severity."}, None, {})

        self.assertGreater(context["tokenEstimate"], 0)
        self.assertIsInstance(context["tokenEstimate"], int)
        self.assertEqual(PlanningEngine().build_planning_context({"id": 501, "type": "Task", "title": "Add fault filter", "description": "Filter fault events."}, None, {})["workItemId"], 501)


if __name__ == "__main__":
    unittest.main()
