from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.execution import ExecutionPackageBuilder, ExecutionPackageService, ExecutionRequest, build_execution_package_v2
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


def planning_candidate():
    return {"candidateId": "planning-1", "sourceType": "Planning", "category": "Planning", "title": "Add fault detail", "content": "Implement fault detail", "confidenceScore": .9, "provenance": {"artifactId": "story-1"}}


def capsule(*items, mode="Unavailable", confidence=.8, rejected=None):
    return {"requestId": "ctx-1", "correlationId": "corr-1", "capsuleVersion": "3.1", "confidence": confidence, "freshnessStatus": "Fresh", "repositorySnapshotVersion": "snap-1", "selectedContext": list(items), "rejectedContext": rejected or [], "diagnostics": {"repositoryMode": mode}, "acceptanceCriteria": ["Authorized users can view fault detail."]}


class ExecutionPackageMilestone33Tests(unittest.TestCase):
    def setUp(self): self.builder = ExecutionPackageBuilder()

    def test_planning_only_package_is_deterministic_and_needs_review(self):
        package = self.builder.build(capsule(planning_candidate()), ExecutionRequest("ImplementationPackage", story_id="story-1"))
        self.assertEqual(package["repositoryContext"]["repositoryMode"], "Unavailable")
        self.assertEqual(package["metadata"]["status"], "Needs Review")
        self.assertFalse(package["diagnostics"]["llmUsed"])
        self.assertFalse(package["diagnostics"]["retrievalPerformed"])

    def test_code_indexed_repository_uses_only_capsule_evidence(self):
        file_item = {"sourceType": "Repository", "category": "File", "title": "src/FaultController.cs", "content": "direct file", "confidenceScore": .95}
        api_item = {"sourceType": "Repository", "category": "API", "title": "GET /faults/{id}", "content": "direct api", "confidenceScore": .9}
        package = self.builder.build(capsule(planning_candidate(), file_item, api_item, mode="CodeIndexed"), ExecutionRequest("ImplementationPackage", story_id="story-1"))
        self.assertEqual(package["repositoryContext"]["relevantFiles"], ["src/FaultController.cs"])
        self.assertEqual(package["implementationGuidance"]["recommendedAPIs"], ["GET /faults/{id}"])

    def test_knowledge_snapshot_never_returns_file_or_api_evidence(self):
        file_item = {"sourceType": "Repository", "category": "File", "title": "invented.py", "content": "bad", "confidenceScore": .9}
        module = {"sourceType": "Repository", "category": "Module", "title": "Fault Monitoring", "content": "module", "confidenceScore": .8}
        package = self.builder.build(capsule(planning_candidate(), file_item, module, mode="KnowledgeSnapshot"), ExecutionRequest("ImplementationPackage", story_id="story-1"))
        self.assertEqual(package["repositoryContext"]["relevantFiles"], [])
        self.assertEqual(package["repositoryContext"]["relevantModules"], ["Fault Monitoring"])

    def test_low_confidence_and_missing_acceptance_are_blocked(self):
        value = capsule(planning_candidate(), confidence=.2)
        value["acceptanceCriteria"] = []
        package = self.builder.build(value, ExecutionRequest("ImplementationPackage", story_id="story-1"))
        self.assertEqual(package["metadata"]["status"], "Blocked")
        self.assertLess(package["metadata"]["executionReadiness"], 75)

    def test_blocked_module_acceptance_mapping_and_qa_guidance(self):
        rejected = [{"candidate": {"category": "Module", "title": "Firmware"}, "reason": "blocked_module"}]
        package = self.builder.build(capsule(planning_candidate(), rejected=rejected), ExecutionRequest("ImplementationPackage", story_id="story-1"))
        self.assertEqual(package["implementationGuidance"]["blockedModules"], ["Firmware"])
        self.assertEqual(package["validationGuidance"]["acceptanceMapping"][0]["acceptanceCriteriaId"], "AC001")
        self.assertTrue(package["qaGuidance"]["suggestedTests"])
        self.assertTrue(package["qaGuidance"]["negativeTests"])
        self.assertIn("developerPrompt", package["tokenGuidance"])

    def test_service_persists_and_emits_platform_events(self):
        with tempfile.TemporaryDirectory() as temp:
            platform = PlatformFoundation(Path(temp) / "platform")
            service = ExecutionPackageService(JsonMapStore(Path(temp) / "packages.json"), platform=platform)
            package = service.build(capsule(planning_candidate()), ExecutionRequest("ImplementationPackage", story_id="story-1"), "corr-1")
            self.assertEqual(service.get(package["packageId"]), package)
            self.assertIsNotNone(service.summary(package["packageId"]))
            self.assertGreater(platform.events.list_recent(event_type="ExecutionPackageBuilt")["count"], 0)
            self.assertGreater(platform.activity.list_recent(activityType="ExecutionPackageGeneration")["count"], 0)

    def test_legacy_builder_keeps_existing_fields_and_adds_canonical_sections(self):
        package = build_execution_package_v2(story={"id": "story-1", "title": "View fault detail"}, selected_task={}, acceptance_criteria=["Fault detail is visible."], context_capsule={"capsuleId": "legacy", "acceptanceCriteria": ["Fault detail is visible."], "confidence": .8})
        self.assertIn("businessContext", package)
        self.assertIn("planningContext", package)
        self.assertIn("qaGuidance", package)
        self.assertFalse(package["diagnostics"]["llmUsed"])


if __name__ == "__main__": unittest.main()
