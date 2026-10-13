from __future__ import annotations

import unittest

from backend.intelligence.planning import buildPlanningContext
from backend.intelligence.reasoning import PlanningReasoner, generatePlanningArtifact, generate_planning_artifact


PROFILE = {
    "applications": [
        {"name": "Operations Dashboard", "type": "Web Portal"},
        {"name": "Firmware Service", "type": "Firmware"},
    ],
    "knowledge_registry": {
        "modules": ["Dashboard", "Fault Monitoring", "Telemetry", "Device Health", "Firmware"],
        "flows": ["Dashboard Monitoring", "Fault Review", "Investigation", "Telemetry Review", "Firmware Rollout"],
        "dependencies": ["Telemetry owner alignment"],
        "standards": ["Acceptance criteria traceability", "Repository-ranked files only"],
    },
}

REPOSITORY = {
    "modules": [
        {"name": "Fault Monitoring", "path": "backend/faults/service.py", "keywords": ["fault", "outage"]},
        {"name": "Telemetry", "path": "backend/telemetry/service.py", "keywords": ["telemetry"]},
        {"name": "Firmware", "path": "backend/firmware/service.py", "keywords": ["firmware"]},
    ],
    "flows": ["Fault Review", "Investigation", "Telemetry Review", "Firmware Rollout"],
}


class FakeProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompt = ""
        self.output_type = ""

    def generate_json(self, prompt: str, output_type: str) -> dict:
        self.prompt = prompt
        self.output_type = output_type
        return self.payload


def make_context(work_item: dict, parent: dict | None = None, existing_children: list[dict] | None = None) -> dict:
    return buildPlanningContext(
        work_item,
        parent or work_item,
        {
            "projectProfile": PROFILE,
            "repositorySnapshot": REPOSITORY,
            "knowledgeRegistry": PROFILE["knowledge_registry"],
            "existingChildren": existing_children or [],
        },
    )


def artifact_titles(result: dict) -> list[str]:
    return [artifact["title"] for artifact in result["artifacts"]]


class ReasoningIntelligenceTests(unittest.TestCase):
    def test_dashboard_epic_generates_feature_artifacts_from_planning_context(self) -> None:
        context = make_context(
            {
                "id": 700,
                "type": "Epic",
                "title": "Modernize operations dashboard",
                "description": "Provide live dashboard monitoring, operational status, reporting, and production health visibility.",
            }
        )

        result = generatePlanningArtifact(context, "Feature")

        titles = artifact_titles(result)
        self.assertTrue(any("Dashboard" in title or "Operational" in title for title in titles))
        self.assertTrue(result["artifacts"])
        first = result["artifacts"][0]
        self.assertEqual(first["validationStatus"], "Pending")
        self.assertIn("Dashboard", first["generatedUsing"]["modules"])
        self.assertIn("Dashboard Monitoring", first["generatedUsing"]["flows"])
        self.assertNotIn("knowledge_registry", result["prompt"])
        self.assertLess(result["diagnostics"]["promptTokensEstimate"], 450)

    def test_outage_feature_generates_sprint_ready_stories_without_firmware_leakage(self) -> None:
        epic = {"id": 700, "type": "Epic", "title": "Operations dashboard", "description": "Dashboard and outage investigation."}
        context = make_context(
            {
                "id": 701,
                "type": "Feature",
                "title": "Outage Investigation Workspace",
                "description": "Operators investigate outage root cause from fault events and telemetry timeline.",
            },
            epic,
        )

        result = generate_planning_artifact(context, "Story")
        combined = " ".join(str(artifact) for artifact in result["artifacts"])

        self.assertIn("Investigation", combined)
        self.assertIn("Fault Monitoring", result["artifacts"][0]["generatedUsing"]["modules"])
        self.assertNotIn("Firmware Rollout", combined)
        self.assertNotIn("Firmware", result["artifacts"][0]["generatedUsing"]["modules"])

    def test_investigation_story_generates_tasks_from_modules_flows_and_acceptance_context(self) -> None:
        feature = {"id": 701, "type": "Feature", "title": "Outage Investigation Workspace", "description": "Investigate outage from fault events."}
        context = make_context(
            {
                "id": 702,
                "type": "Story",
                "title": "Start investigation from fault event",
                "description": "As an Operations User, I want to start investigation from a fault event so that I can triage outage impact.",
                "acceptanceCriteria": [
                    "Investigation starts from a selected critical fault event.",
                    "Telemetry and device health context are visible.",
                ],
            },
            feature,
        )

        result = generatePlanningArtifact(context, "Task")

        self.assertTrue(any(title.startswith("Build") for title in artifact_titles(result)))
        combined = " ".join(str(artifact) for artifact in result["artifacts"])
        self.assertIn("Fault Monitoring", combined)
        self.assertIn("Investigation", combined)
        self.assertNotIn("Firmware", combined)

    def test_provider_payload_is_sanitized_and_does_not_allow_rejected_context(self) -> None:
        context = make_context(
            {
                "id": 703,
                "type": "Story",
                "title": "Review outage investigation timeline",
                "description": "Operations User reviews outage event timeline and telemetry.",
            }
        )
        provider = FakeProvider(
            {
                "artifacts": [
                    {
                        "title": "Review outage investigation timeline",
                        "description": "Use Firmware Rollout and Investigation to review outage timeline.",
                        "businessValue": "Firmware Rollout improves outage review.",
                        "acceptanceCriteria": ["Firmware Rollout is visible.", "Investigation is visible."],
                        "dependencies": ["Telemetry owner alignment", "Firmware owner alignment"],
                        "confidence": 0.95,
                    }
                ]
            }
        )

        result = PlanningReasoner(provider).generate_planning_artifact(context, "Story")
        combined = " ".join(str(artifact) for artifact in result["artifacts"])

        self.assertNotIn("Firmware Rollout", combined)
        self.assertTrue(result["diagnostics"]["validationWarnings"])
        self.assertEqual(result["diagnostics"]["providerUsed"], "llm")

    def test_duplicate_feature_returns_duplicate_candidate(self) -> None:
        context = make_context(
            {
                "id": 704,
                "type": "Epic",
                "title": "Critical fault monitoring",
                "description": "Detect critical fault events on the operations dashboard.",
            },
            existing_children=[
                {
                    "id": 900,
                    "type": "Feature",
                    "title": "Critical Fault Detection",
                    "description": "Detect critical fault events on operations dashboard.",
                }
            ],
        )

        result = generatePlanningArtifact(context, "Feature")

        self.assertTrue(any(artifact["artifactType"] == "Duplicate Candidate" for artifact in result["artifacts"]))
        self.assertTrue(any(artifact.get("duplicateCandidate") for artifact in result["artifacts"]))

    def test_acceptance_criteria_are_derived_and_present(self) -> None:
        context = make_context(
            {
                "id": 705,
                "type": "Feature",
                "title": "Outage Investigation Workspace",
                "description": "Operators investigate outage root cause from fault events.",
            }
        )

        result = generatePlanningArtifact(context, "Story")

        for artifact in result["artifacts"]:
            self.assertTrue(artifact["acceptanceCriteria"])
            self.assertTrue(any("flow" in item.lower() or "feature intent" in item.lower() for item in artifact["acceptanceCriteria"]))

    def test_role_changes_prompt_correctly(self) -> None:
        context = make_context({"id": 706, "type": "Story", "title": "Start investigation", "description": "Investigate fault event."})

        task_result = generatePlanningArtifact(context, "Task")
        story_result = generatePlanningArtifact(context, "Story")
        epic_result = generatePlanningArtifact(context, "Epic")

        self.assertIn("Senior Developer", task_result["prompt"])
        self.assertIn("Scrum Master / Business Analyst", story_result["prompt"])
        self.assertIn("Product Owner", epic_result["prompt"])

    def test_rejects_broad_context_input(self) -> None:
        context = make_context({"id": 707, "type": "Story", "title": "Start investigation", "description": "Investigate fault event."})
        context["knowledge_registry"] = {"modules": ["Firmware"]}

        with self.assertRaises(ValueError):
            generatePlanningArtifact(context, "Story")


if __name__ == "__main__":
    unittest.main()

