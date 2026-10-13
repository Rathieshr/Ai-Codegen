from __future__ import annotations

import unittest

from backend.intelligence.planning import buildPlanningContext
from backend.intelligence.reasoning import generatePlanningArtifact
from backend.intelligence.validation import ValidationEngine, validateArtifact, validate_artifact


PROFILE = {
    "applications": [{"name": "Operations Dashboard", "type": "Web Portal"}],
    "knowledge_registry": {
        "modules": ["Dashboard", "Fault Monitoring", "Telemetry", "Device Health"],
        "flows": ["Fault Review", "Investigation", "Telemetry Review", "Dashboard Monitoring"],
        "dependencies": ["Telemetry owner alignment"],
        "standards": ["Acceptance criteria traceability", "Repository-ranked files only"],
        "terminology": ["Fault Event", "Telemetry", "Outage"],
    },
}

REPOSITORY = {
    "rankedFiles": [
        {"path": "backend/faults/service.py", "score": 0.91},
        {"path": "backend/telemetry/service.py", "score": 0.89},
    ],
    "source_files": ["backend/faults/service.py", "backend/telemetry/service.py"],
}


def make_context(work_item: dict, parent: dict | None = None, siblings: list[dict] | None = None) -> dict:
    return buildPlanningContext(
        work_item,
        parent or work_item,
        {
            "projectProfile": PROFILE,
            "knowledgeRegistry": PROFILE["knowledge_registry"],
            "repositorySnapshot": REPOSITORY,
            "existingChildren": siblings or [],
        },
    )


def good_feature_artifact(context: dict) -> dict:
    artifact = generatePlanningArtifact(context, "Feature")["artifacts"][0]
    artifact["description"] += " Acceptance criteria traceability and Repository-ranked files only are enforced."
    artifact["acceptanceCriteria"] = [
        "Operations User can review critical fault event status in the dashboard.",
        "Fault Event details display telemetry freshness and device health context.",
        "Outage investigation behavior is traceable to selected PlanningContext.",
    ]
    return artifact


class ValidationIntelligenceTests(unittest.TestCase):
    def test_epic_to_feature_alignment_can_be_approved(self) -> None:
        context = make_context(
            {
                "id": 800,
                "type": "Epic",
                "title": "Modernize operations dashboard",
                "description": "Provide live dashboard monitoring for fault events, telemetry, and outage investigation.",
            }
        )
        report = validateArtifact(context, good_feature_artifact(context), {"repositorySnapshot": REPOSITORY, "knowledgeRegistry": PROFILE["knowledge_registry"]})

        self.assertIn(report["validationStatus"], ["Approved", "NeedsReview"])
        self.assertGreaterEqual(report["businessAlignment"], 60)
        self.assertGreaterEqual(report["capabilityAlignment"], 70)
        self.assertGreaterEqual(report["repositoryAlignment"], 80)
        self.assertGreater(report["confidence"], 0.5)

    def test_feature_to_story_alignment_detects_unrelated_capability(self) -> None:
        context = make_context(
            {
                "id": 801,
                "type": "Feature",
                "title": "Outage Investigation Workspace",
                "description": "Operators investigate outage root cause from fault event telemetry.",
            }
        )
        artifact = {
            "title": "Reliability Analytics Dashboard",
            "description": "Provide analytics trend dashboard unrelated to outage investigation.",
            "businessValue": "Trend reporting.",
            "acceptanceCriteria": ["The system should work."],
            "generatedUsing": {
                "planningContextVersion": "test",
                "capabilities": ["Reliability Analytics"],
                "modules": ["Analytics"],
                "flows": ["Analytics Review"],
                "applications": [],
                "standards": [],
            },
        }

        report = validate_artifact(context, artifact)

        self.assertEqual(report["validationStatus"], "Rejected")
        self.assertTrue(any(issue["category"] == "Capability Alignment" for issue in report["issues"]))
        self.assertTrue(any(issue["category"] == "Repository Alignment" for issue in report["issues"]))

    def test_story_to_task_alignment_scores_execution_readiness(self) -> None:
        context = make_context(
            {
                "id": 802,
                "type": "Story",
                "title": "Start investigation from fault event",
                "description": "As an Operations User, I want to start an outage investigation from a fault event so that I can triage telemetry context.",
                "acceptanceCriteria": ["Operations User can start investigation from a selected fault event."],
            }
        )
        task = generatePlanningArtifact(context, "Task")["artifacts"][0]

        report = ValidationEngine().validate_artifact(context, task, {"repositorySnapshot": REPOSITORY})

        self.assertGreaterEqual(report["engineeringReadiness"], 65)
        self.assertGreaterEqual(report["executionReadiness"], 60)
        self.assertIn(report["validationStatus"], ["Approved", "NeedsReview"])

    def test_duplicate_features_return_duplicate_warning(self) -> None:
        context = make_context(
            {
                "id": 803,
                "type": "Epic",
                "title": "Critical fault monitoring",
                "description": "Detect and review critical fault events.",
            },
            siblings=[{"id": 900, "type": "Feature", "title": "Critical Fault Detection", "description": "Detect and review critical fault events."}],
        )
        artifact = {
            "title": "Critical Fault Detection",
            "description": "Detect and review critical fault events with severity and event detail context.",
            "businessValue": "Faster detection of critical fault events.",
            "acceptanceCriteria": [
                "Operations User can view active critical fault events.",
                "Fault event details include severity, event time, and current status.",
            ],
            "generatedUsing": {
                "planningContextVersion": "test",
                "capabilities": ["Fault Monitoring"],
                "modules": ["Fault Monitoring", "Telemetry"],
                "flows": ["Fault Event Review", "Fault Detail Review"],
                "applications": ["Operations Dashboard"],
                "standards": [],
            },
        }

        report = validateArtifact(context, artifact)

        self.assertGreaterEqual(report["duplicateRisk"], 75)
        self.assertTrue(any(issue["category"] == "Duplicate Detection" for issue in report["issues"]))
        self.assertIn(report["validationStatus"], ["NeedsReview", "Rejected"])

    def test_distinct_canonical_capabilities_are_not_duplicate_features(self) -> None:
        context = make_context(
            {
                "id": 810,
                "type": "Epic",
                "title": "Modernize operations dashboard",
                "description": "Improve critical fault monitoring and live operations awareness.",
            },
            siblings=[{"id": 901, "type": "Feature", "title": "Critical Fault Detection", "description": "Detect and review critical fault events immediately."}],
        )
        artifact = {
            "title": "Live Operations Awareness",
            "description": "Provide a shared live view of operational status and monitoring context.",
            "businessValue": "Improve operational awareness.",
            "acceptanceCriteria": [
                "Operations User can review live operational status in a dashboard.",
                "Operations status updates are visible within 60 seconds.",
            ],
            "generatedUsing": {
                "planningContextVersion": "test",
                "capabilities": ["Operational Awareness"],
                "modules": ["Telemetry", "Dashboard"],
                "flows": ["Live Status Review", "Operations Monitoring"],
                "applications": ["Operations Dashboard"],
                "standards": [],
            },
        }

        report = validateArtifact(context, artifact)

        self.assertLess(report["duplicateRisk"], 75)
        self.assertFalse(any(issue["category"] == "Duplicate Detection" for issue in report["issues"]))

    def test_validation_rejects_system_names_used_as_flows(self) -> None:
        context = make_context(
            {
                "id": 811,
                "type": "Feature",
                "title": "Critical Fault Detection",
                "description": "Detect and review critical fault events.",
            }
        )
        artifact = good_feature_artifact(context)
        artifact["generatedUsing"]["flows"] = ["Analytics Platform", "Mobile Application"]

        report = validateArtifact(context, artifact)

        self.assertEqual(report["validationStatus"], "Rejected")
        self.assertTrue(any(issue["category"] == "Flow Alignment" for issue in report["issues"]))

    def test_repository_mismatch_rejects_hallucinated_module(self) -> None:
        context = make_context({"id": 804, "type": "Story", "title": "Review fault event", "description": "Review fault event telemetry."})
        artifact = generatePlanningArtifact(context, "Task")["artifacts"][0]
        artifact["generatedUsing"]["modules"] = ["Firmware"]
        artifact["description"] += " Firmware work is required."

        report = validateArtifact(context, artifact)

        self.assertEqual(report["validationStatus"], "Rejected")
        self.assertTrue(any("Unsupported modules" in issue["message"] for issue in report["issues"]))

    def test_repository_mismatch_rejects_hallucinated_files(self) -> None:
        context = make_context({"id": 805, "type": "Story", "title": "Review fault event", "description": "Review fault event telemetry."})
        artifact = generatePlanningArtifact(context, "Task")["artifacts"][0]
        artifact["repositoryFiles"] = ["backend/fake/firmware.py"]

        report = validateArtifact(context, artifact, {"repositorySnapshot": REPOSITORY})

        self.assertEqual(report["validationStatus"], "Rejected")
        self.assertTrue(any("Repository files are not known" in issue["message"] for issue in report["issues"]))

    def test_missing_acceptance_criteria_rejects_artifact(self) -> None:
        context = make_context({"id": 806, "type": "Feature", "title": "Outage Investigation", "description": "Investigate outage from fault event."})
        artifact = good_feature_artifact(context)
        artifact["acceptanceCriteria"] = []

        report = validateArtifact(context, artifact)

        self.assertEqual(report["validationStatus"], "Rejected")
        self.assertTrue(any(issue["category"] == "Acceptance Criteria" for issue in report["issues"]))

    def test_invalid_acceptance_criteria_are_rejected_or_needs_review(self) -> None:
        context = make_context({"id": 807, "type": "Feature", "title": "Outage Investigation", "description": "Investigate outage from fault event."})
        artifact = good_feature_artifact(context)
        artifact["acceptanceCriteria"] = ["The system should work."]

        report = validateArtifact(context, artifact)

        self.assertIn(report["validationStatus"], ["Rejected", "NeedsReview"])
        self.assertTrue(any("Vague acceptance criteria" in issue["message"] for issue in report["issues"]))

    def test_knowledge_mismatch_adds_actionable_warning(self) -> None:
        context = make_context({"id": 808, "type": "Feature", "title": "Outage Investigation", "description": "Investigate outage from fault event."})
        artifact = good_feature_artifact(context)
        artifact["description"] = artifact["description"].replace("Acceptance criteria traceability and Repository-ranked files only are enforced.", "")

        report = validateArtifact(context, artifact, {"knowledgeRegistry": PROFILE["knowledge_registry"]})

        self.assertTrue(any(issue["category"] == "Knowledge Alignment" for issue in report["issues"]))
        self.assertIn(report["validationStatus"], ["Approved", "NeedsReview"])

    def test_sprint_readiness_invest_validation_for_story(self) -> None:
        context = make_context(
            {
                "id": 809,
                "type": "Feature",
                "title": "Outage Investigation Workspace",
                "description": "Operators investigate outage root cause from fault events.",
            }
        )
        story = generatePlanningArtifact(context, "Story")["artifacts"][0]

        report = validateArtifact(context, story)

        self.assertGreaterEqual(report["sprintReadiness"], 70)
        self.assertTrue(report["recommendations"])


if __name__ == "__main__":
    unittest.main()
