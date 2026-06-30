from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from backend.intelligence.dna import (
    compareDNA,
    dnaToGraph,
    generateDNA,
    getDNAHistory,
    inheritDNA,
    mergeDNA,
    validateDNA,
)
from backend.project_intelligence import ProjectIntelligenceService


def _profile() -> dict:
    return {
        "project_name": "LineDefender",
        "domain": "Utility Grid Management",
        "applications": [{"name": "Operations Dashboard", "type": "Web Portal"}],
        "knowledge_registry": {
            "modules": ["Fault Monitoring", "Telemetry", "Asset Health"],
            "flows": ["Fault Event Review Flow", "Outage Investigation Flow"],
            "source_files": ["README.md"],
        },
        "development_standards": {
            "security_requirements": ["Role-based access"],
            "coding_guidelines": ["Repository pattern"],
            "testing_requirements": ["Unit tests required"],
        },
    }


class WorkItemDNATests(unittest.TestCase):
    def test_feature_story_task_inherit_parent_dna(self) -> None:
        epic_dna = generateDNA(
            {"id": 109, "title": "Real-Time Fault Event Monitoring"},
            "Epic",
            profile=_profile(),
            epic_analysis={
                "businessProblems": ["Fault events are not visible early enough."],
                "businessGoals": ["Improve operations awareness."],
                "desiredOutcomes": ["Faster outage response."],
                "planningBoundary": {"inScope": ["Fault Event Review"], "outOfScope": ["Firmware rollout"]},
            },
        )
        feature_dna = generateDNA(
            {
                "id": 201,
                "title": "Critical Fault Detection",
                "business_value": "Faster detection of critical conditions.",
                "affected_modules": ["Fault Monitoring"],
                "affected_flows": ["Fault Event Review Flow"],
            },
            "Feature",
            profile=_profile(),
            parent_dna=epic_dna,
        )
        story_dna = generateDNA(
            {
                "id": 301,
                "title": "Open critical fault event details",
                "acceptance_criteria": ["Operations user can view fault severity."],
            },
            "Story",
            profile=_profile(),
            parent_dna=feature_dna,
        )
        task_dna = generateDNA(
            {"id": 401, "title": "Add fault event details API", "files": ["FaultEventController.cs"]},
            "Task",
            profile=_profile(),
            parent_dna=story_dna,
        )

        self.assertEqual(feature_dna["parentDNA"], epic_dna["dnaId"])
        self.assertEqual(story_dna["parentDNA"], feature_dna["dnaId"])
        self.assertEqual(task_dna["parentDNA"], story_dna["dnaId"])
        self.assertEqual(story_dna["businessGoals"], epic_dna["businessGoals"])
        self.assertIn("Fault Monitoring", task_dna["repositoryEvidence"]["modules"])
        self.assertIn("FaultEventController.cs", task_dna["repositoryEvidence"]["files"])

    def test_validation_rejects_capability_change_boundary_expansion_and_unrelated_modules(self) -> None:
        parent = generateDNA(
            {"id": 1, "title": "Critical Fault Detection", "capability": "Fault Monitoring", "affected_modules": ["Fault Monitoring"]},
            "Epic",
            profile=_profile(),
            epic_analysis={"planningBoundary": {"inScope": ["Fault Event Review"], "outOfScope": []}},
        )
        invalid_child = {
            **parent,
            "dnaId": "dna_invalid_child",
            "workItemType": "Story",
            "parentDNA": parent["dnaId"],
            "capability": "Firmware Management",
            "planningBoundary": {"inScope": ["Fault Event Review", "Firmware Rollout"], "outOfScope": []},
            "repositoryEvidence": {"modules": ["Fault Monitoring", "Firmware Management"], "flows": [], "applications": [], "services": [], "files": []},
        }

        result = validateDNA(parent, invalid_child)

        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "Rejected")
        self.assertTrue(any("capability" in issue for issue in result["issues"]))
        self.assertTrue(any("planning boundary" in issue for issue in result["issues"]))
        self.assertTrue(any("unrelated modules" in issue for issue in result["issues"]))

    def test_merge_dna_preserves_immutable_identity_and_versions_history(self) -> None:
        dna = generateDNA(
            {"id": 501, "title": "Fault Event Review", "capability": "Fault Monitoring"},
            "Story",
            profile=_profile(),
        )
        updated = mergeDNA(
            dna,
            {
                "capability": "Firmware Management",
                "businessGoals": ["Overwrite goal"],
                "responsibilities": ["Show severity"],
                "dependencies": ["Telemetry freshness"],
            },
        )
        diff = compareDNA(dna, updated)

        self.assertEqual(updated["capability"], dna["capability"])
        self.assertEqual(updated["businessGoals"], dna["businessGoals"])
        self.assertIn("Show severity", updated["responsibilities"])
        self.assertIn("Telemetry freshness", updated["dependencies"])
        self.assertEqual(updated["version"], dna["version"] + 1)
        self.assertGreaterEqual(len(getDNAHistory(dna["dnaId"])), 2)
        self.assertTrue(diff["changed"])

    def test_inherit_dna_records_graph_relationships(self) -> None:
        parent = generateDNA(
            {"id": 601, "title": "Outage Investigation", "capability": "Outage Investigation", "affected_modules": ["Fault Monitoring"], "affected_flows": ["Outage Investigation Flow"]},
            "Feature",
            profile=_profile(),
        )
        child = inheritDNA(parent, {"id": 602, "responsibilities": ["Start investigation from event"]}, "Story")
        graph = dnaToGraph(child)

        self.assertEqual(child["parentDNA"], parent["dnaId"])
        self.assertTrue(any(edge["type"] == "inherits" and edge["to"] == parent["dnaId"] for edge in graph["edges"]))
        self.assertTrue(any(node["type"] == "Module" and node["name"] == "Fault Monitoring" for node in graph["nodes"]))

    def test_execution_package_and_capsule_consume_work_item_dna(self) -> None:
        story = {
            "id": 701,
            "title": "Open critical fault event details",
            "description": "As an Operations User, I want to view critical fault event details.",
            "acceptance_criteria": ["Fault severity and timestamp are visible."],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            result = ProjectIntelligenceService().build_execution_context(story, _profile(), options={"force_provider": "deterministic_fallback"})

        self.assertTrue(result["work_item_dna"]["dnaId"])
        self.assertEqual(result["context_capsule"]["workItemDNA"]["dnaId"], result["work_item_dna"]["dnaId"])
        self.assertEqual(result["context_capsule_diagnostics"]["dnaId"], result["work_item_dna"]["dnaId"])
        self.assertEqual(result["dna_summary"]["capability"], result["work_item_dna"]["capability"])
        self.assertIn("Fault Monitoring", result["dna_summary"]["modules"])
        self.assertIn("score", result["dna_validation"]["summary"])

    def test_feature_generation_uses_feature_dna_and_children_inherit_it(self) -> None:
        feature_dna = generateDNA(
            {
                "id": 801,
                "title": "Critical Fault Detection",
                "capability": "Fault Monitoring",
                "affected_modules": ["Fault Monitoring"],
                "affected_flows": ["Fault Event Review Flow"],
            },
            "Feature",
            profile=_profile(),
        )

        result = ProjectIntelligenceService().refine_feature(
            {"id": 801, "title": "Critical Fault Detection", "work_item_dna": feature_dna},
            _profile(),
            options={"force_provider": "deterministic_fallback"},
        )

        self.assertEqual(result["work_item_dna"]["dnaId"], feature_dna["dnaId"])
        self.assertEqual(result["dna_validation"]["status"], "Approved")
        self.assertTrue(result["recommended_stories"])
        self.assertTrue(all(story["work_item_dna"]["parentDNA"] == feature_dna["dnaId"] for story in result["recommended_stories"]))

    def test_story_generation_uses_story_dna_and_tasks_inherit_it(self) -> None:
        story_dna = generateDNA(
            {
                "id": 901,
                "title": "Open critical fault event details",
                "capability": "Fault Monitoring",
                "affected_modules": ["Fault Monitoring"],
                "affected_flows": ["Fault Event Review Flow"],
                "acceptance_criteria": ["Fault severity is visible."],
            },
            "Story",
            profile=_profile(),
        )

        result = ProjectIntelligenceService().refine_story(
            {"id": 901, "title": "Open critical fault event details", "work_item_dna": story_dna},
            _profile(),
            options={"force_provider": "deterministic_fallback"},
        )

        self.assertEqual(result["work_item_dna"]["dnaId"], story_dna["dnaId"])
        self.assertEqual(result["dna_validation"]["status"], "Approved")
        self.assertTrue(result["proposed_tasks"])
        self.assertTrue(all(task["work_item_dna"]["parentDNA"] == story_dna["dnaId"] for task in result["proposed_tasks"]))

    def test_invalid_dna_blocks_story_generation(self) -> None:
        feature_dna = generateDNA(
            {"id": 1001, "title": "Critical Fault Detection", "capability": "Fault Monitoring", "affected_modules": ["Fault Monitoring"]},
            "Feature",
            profile=_profile(),
        )
        invalid_story_dna = {
            **feature_dna,
            "dnaId": "dna_invalid_story",
            "workItemId": 1002,
            "workItemType": "Story",
            "parentDNA": feature_dna["dnaId"],
            "capability": "Firmware Management",
            "repositoryEvidence": {"modules": ["Fault Monitoring", "Firmware Management"], "flows": [], "applications": [], "services": [], "files": []},
        }

        result = ProjectIntelligenceService().refine_story(
            {"id": 1002, "title": "Update firmware rollout visibility", "work_item_dna": invalid_story_dna},
            _profile(),
            options={"parent_dna": feature_dna, "force_provider": "deterministic_fallback"},
        )

        self.assertTrue(result["blocked"])
        self.assertEqual(result["failure_reason"], "dna_validation_failed")
        self.assertEqual(result["dna_validation"]["status"], "Rejected")

    def test_missing_dna_is_generated_before_feature_generation_continues(self) -> None:
        result = ProjectIntelligenceService().refine_feature(
            {"id": 1101, "title": "Critical Fault Detection", "description": "Review critical fault events."},
            _profile(),
            options={"force_provider": "deterministic_fallback"},
        )

        self.assertTrue(result["work_item_dna"]["dnaId"])
        self.assertEqual(result["work_item_dna"]["workItemType"], "Feature")
        self.assertEqual(result["dna_validation"]["status"], "Approved")
        self.assertTrue(result["recommended_stories"])

    def test_developer_prompt_includes_execution_package_dna_only(self) -> None:
        story_dna = generateDNA(
            {
                "id": 1201,
                "title": "Open critical fault event details",
                "capability": "Fault Monitoring",
                "business_value": "Faster outage triage.",
                "responsibilities": ["Show fault severity and device context"],
                "affected_modules": ["Fault Monitoring"],
                "affected_flows": ["Fault Event Review Flow"],
                "acceptance_criteria": ["Fault severity is visible."],
            },
            "Story",
            profile=_profile(),
        )

        result = ProjectIntelligenceService().build_dev_prompt(
            {"id": 1201, "title": "Open critical fault event details", "work_item_dna": story_dna},
            _profile(),
            options={"force_provider": "deterministic_fallback"},
        )

        self.assertIn("# Engineering DNA", result["prompt"])
        self.assertIn("Capability: Fault Monitoring", result["prompt"])
        self.assertIn("Responsibilities: Show fault severity and device context", result["prompt"])


if __name__ == "__main__":
    unittest.main()
