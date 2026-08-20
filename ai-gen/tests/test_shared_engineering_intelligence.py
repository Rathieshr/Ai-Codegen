from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.engineering_intelligence.providers import AcceptanceCriteriaProvider
from backend.engineering_intelligence.shared_orchestrator import HEIIntelligenceOrchestrator
from backend.engineering_intelligence.services.context_builder import ContextBuilder
from backend.platform.shared import JsonMapStore


class EngineeringIntelligenceStub:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_planning_context(self, requirement, *, correlation_id=""):
        self.calls.append(dict(requirement))
        project_id = requirement.get("projectId") or "project-1"
        return {
            "engineeringContext": {
                "contextId": f"ctx-{requirement.get('workItemId') or requirement.get('requirementId') or 'new'}",
                "contextVersion": "v1",
                "requirement": requirement,
                "repository": {
                    "repositoryId": requirement.get("repositoryId") or "repo-1",
                    "repositorySnapshotVersion": "snapshot-7",
                    "files": [{"path": "src/device.ts", "source": "Repository", "confidence": 90}],
                },
                "azureDevOps": {"projectId": project_id},
                "engineeringMemory": {"matches": []},
                "similarWork": {"matches": [{
                    "workItem": {"id": "102", "title": "Existing device story", "type": "Story"},
                    "confidence": 88,
                    "reason": "Intent overlap",
                }]},
                "architecture": {"evidence": []},
                "dependencies": {},
                "projectIntelligence": {
                    "approvedArtifacts": [{
                        "id": "approved-1", "title": "Device pattern",
                        "source": "Project Intelligence", "confidence": 86,
                    }],
                    "rejectedContext": [{"name": "Other project", "reason": "scope mismatch"}],
                },
                "repository_markdown_context": {
                    "selected": [{
                        "evidenceId": "doc-1", "path": "docs/device.md",
                        "heading": "Device", "source": "Repository Markdown", "confidence": 82,
                    }],
                    "rejected": [{"path": "docs/unrelated.md"}],
                    "conflicts": [],
                },
                "relevantDocumentation": [{
                    "evidenceId": "doc-1", "path": "docs/device.md",
                    "heading": "Device", "source": "Repository Markdown", "confidence": 82,
                }],
                "impact": {}, "reuse": {}, "readiness": {},
                "sourceVersions": {"projectKnowledgeVersion": "knowledge-3"},
                "correlationId": correlation_id,
            },
            "rawContext": {"rejectedContext": [{"name": "must-not-reach-prompt"}]},
            "analysis": {},
            "planningRecommendationInput": {},
        }


class WorkItemProviderStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def build_work_item_context(self, work_item_id, project_id="", *, analyze=False, **_options):
        self.calls.append((str(work_item_id), bool(analyze)))
        if str(work_item_id) not in {"101", "102"}:
            return {"available": False}
        return {
            "available": True,
            "workItem": {
                "id": str(work_item_id), "workItemId": str(work_item_id),
                "workItemType": "Story" if str(work_item_id) == "101" else "Feature",
                "title": "Monitor device health" if str(work_item_id) == "101" else "Existing device story",
                "description": "Operators review current device health.",
                "acceptanceCriteria": ["Current health is visible."],
                "revision": 4, "projectId": project_id or "project-1",
            },
            "analysis": {
                "analysisId": f"analysis-{work_item_id}", "businessGoal": "Reduce device downtime.",
                "confidence": .84, "evidence": [{
                    "sourceType": "WorkItem", "sourceId": str(work_item_id), "confidence": 84,
                }],
                "rejectedContext": [{"name": "wrong project"}],
            },
            "hierarchy": {"parents": [], "children": []},
            "similarItems": [], "acceptanceCriteria": ["Current health is visible."],
            "acceptanceCriteriaAnalysis": {"score": 90},
            "recommendations": [],
        }


class AcceptanceServiceStub:
    def __init__(self) -> None:
        self.calls = 0

    def get_profile(self):
        return {"project_name": "Device Platform"}

    def generate_requirement_acceptance_criteria(self, requirement, profile, options=None):
        self.calls += 1
        return {
            "acceptanceCriteria": ["Given a device, when health loads, then current status is visible."],
            "provider_used": "azure_phi", "source": "project_intelligence",
            "requirement": requirement, "profile": profile, "options": options or {},
        }


class SharedEngineeringIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engineering = EngineeringIntelligenceStub()
        self.work_items = WorkItemProviderStub()
        self.acceptance_service = AcceptanceServiceStub()
        self.service = HEIIntelligenceOrchestrator(
            JsonMapStore(Path(self.temp.name) / "contexts.json"),
            engineering_intelligence=self.engineering,
            work_item_intelligence=self.work_items,
            acceptance_criteria=AcceptanceCriteriaProvider(self.acceptance_service),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_new_requirement_from_custom_hub(self):
        result = self.service.build_context({
            "entryMode": "PROJECT_HUB", "projectId": "project-1",
            "requirement": {"requirementId": "req-1", "title": "Monitor devices"},
        })
        self.assertEqual("PROJECT_HUB", result["engineeringContext"]["entryMode"])

    def test_existing_story_from_work_item_tab(self):
        result = self.service.analyze_work_item("101", {"projectId": "project-1"})
        context = result["engineeringContext"]
        self.assertEqual("101", context["workItem"]["workItemId"])
        self.assertEqual(("101", True), self.work_items.calls[0])

    def test_existing_feature_from_work_item_tab(self):
        result = self.service.analyze_work_item("102", {"projectId": "project-1"})
        self.assertEqual("Feature", result["engineeringContext"]["workItem"]["workItemType"])

    def test_project_intelligence_reaches_both_flows(self):
        hub = self.service.build_context({"entryMode": "PROJECT_HUB", "projectId": "project-1", "requirement": {"title": "Devices"}})
        item = self.service.analyze_work_item("101", {"projectId": "project-1"})
        self.assertEqual("approved-1", hub["engineeringContext"]["projectIntelligence"]["approvedArtifacts"][0]["id"])
        self.assertEqual("approved-1", item["engineeringContext"]["projectIntelligence"]["approvedArtifacts"][0]["id"])

    def test_work_item_intelligence_reaches_hub_for_related_work(self):
        result = self.service.build_context({"entryMode": "PROJECT_HUB", "projectId": "project-1", "requirement": {"title": "Devices"}})
        self.assertEqual("102", result["engineeringContext"]["relatedWorkItemIntelligence"][0]["workItem"]["workItemId"])
        self.assertIn(("102", False), self.work_items.calls)

    def test_repository_context_remains_authoritative(self):
        context = self.service.analyze_work_item("101", {"projectId": "project-1", "repositoryId": "repo-1"})["engineeringContext"]
        self.assertEqual("snapshot-7", context["repository"]["repositorySnapshotVersion"])
        self.assertEqual("src/device.ts", context["repository"]["files"][0]["path"])

    def test_markdown_knowledge_reaches_both_flows(self):
        context = self.service.analyze_work_item("101", {"projectId": "project-1"})["engineeringContext"]
        self.assertEqual("docs/device.md", context["relevantDocumentation"][0]["path"])

    def test_same_work_item_is_not_duplicated(self):
        context = self.service.analyze_work_item("101", {"projectId": "project-1"})["engineeringContext"]
        ids = [item.get("id") for item in context["relatedWorkItems"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_same_context_can_be_reopened(self):
        context = self.service.analyze_work_item("101", {"projectId": "project-1"})["engineeringContext"]
        self.assertEqual(context, self.service.get_context(context["contextId"]))

    def test_acceptance_criteria_delegates_to_stabilized_provider(self):
        result = self.service.generate_acceptance_criteria({"requirement": {"title": "Device health"}})
        self.assertEqual(1, self.acceptance_service.calls)
        self.assertEqual("azure_phi", result["provider_used"])

    def test_prompt_context_uses_unified_context(self):
        context = self.service.analyze_work_item("101", {"projectId": "project-1"})["engineeringContext"]
        self.assertEqual(context["contextId"], context["promptContext"]["contextId"])
        self.assertEqual("WORK_ITEM", context["promptContext"]["entryMode"])

    def test_rejected_context_does_not_reach_prompt(self):
        context = self.service.analyze_work_item("101", {"projectId": "project-1"})["engineeringContext"]
        prompt = str(context["promptContext"])
        self.assertNotIn("wrong project", prompt)
        self.assertNotIn("scope mismatch", prompt)
        self.assertIn("scope mismatch", str(context["lineage"]["rejectedContext"]))

    def test_context_provenance_retains_versions(self):
        context = self.service.analyze_work_item("101", {"projectId": "project-1"})["engineeringContext"]
        document = next(item for item in context["provenance"] if item["filePath"] == "docs/device.md")
        self.assertEqual("snapshot-7", document["repositoryRevision"])
        self.assertEqual("knowledge-3", document["knowledgeVersion"])

    def test_cross_navigation_preserves_work_item(self):
        result = self.service.analyze_work_item("101", {"projectId": "project-1"})
        self.assertEqual("?view=planning&workItemId=101", result["crossNavigation"]["openInPlanning"])

    def test_provider_unavailable_is_reported_without_context_leak(self):
        service = HEIIntelligenceOrchestrator(
            JsonMapStore(Path(self.temp.name) / "fallback.json"),
            engineering_intelligence=self.engineering,
        )
        result = service.build_context({"entryMode": "REQUIREMENT", "requirement": {"title": "Device health"}})
        self.assertEqual("REQUIREMENT", result["engineeringContext"]["entryMode"])

    def test_optimized_context_excludes_rejected_diagnostics(self):
        optimized = ContextBuilder().build_optimized_context({
            "contextId": "ctx", "contextVersion": "1", "projectIntelligence": {
                "knowledge": {"modules": ["Device"]},
                "rejectedContext": [{"name": "Other Project"}],
            },
            "repository_markdown_context": {"selected": [], "rejected": [{"path": "secret.md"}]},
        })
        self.assertNotIn("rejectedContext", optimized["projectIntelligence"])
        self.assertNotIn("rejected", optimized["repository_markdown_context"])


if __name__ == "__main__":
    unittest.main()
