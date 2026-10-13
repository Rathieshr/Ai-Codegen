from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.planning_integration.intelligence import IntelligentPlanningEngine
from backend.planning_integration.service import RequirementPlanningService
from backend.platform.shared import JsonMapStore


SUMMARY = {
    "requirementId": "req-device-health", "contextVersion": "v3", "analysisId": "analysis-3",
    "projectId": "gridhub", "title": "Modernize Device Health Dashboard",
    "planningRequirement": "Operations users need current device health and offline status.",
    "businessGoals": ["Reduce time to identify unhealthy devices."],
    "functionalRequirements": ["Filter devices by health status."],
    "acceptanceCriteria": ["Offline filter returns only offline devices."],
    "dependencies": ["Device Health API"], "risks": ["Stale telemetry"],
}

WORK_ITEMS = [
    {"workItemId": 101, "workItemType": "Epic", "title": "Modernize Device Health Dashboard", "state": "Active", "revision": 7, "description": "Old scope"},
    {"workItemId": 102, "workItemType": "Feature", "title": "Device Health Overview", "state": "Approved", "revision": 4},
    {"workItemId": 103, "workItemType": "Story", "title": "Filter Devices by Health Status", "state": "New", "revision": 2},
]

REPOSITORY = {
    "mode": "CodeIndexed", "repositoryId": "repo-device", "repositoryName": "Device Operations",
    "repositorySnapshotVersion": "snapshot-v12", "modules": ["Device Health", "Telemetry"],
}


class IntelligentPlanningEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntelligentPlanningEngine(
            work_item_provider=lambda _project: WORK_ITEMS,
            iteration_provider=lambda _project: [{"id": "iteration-1", "name": "Sprint 1"}],
            memory_provider=lambda _query: {"results": [{
                "id": "memory-1", "title": "Device health filter pattern", "category": "Planning Memory",
                "artifactType": "Story", "confidence": 91, "searchScore": 12, "matchReasons": ["keyword", "module"],
            }]},
        )

    def test_context_uses_synchronized_ado_repository_and_approved_memory(self):
        context = self.engine.build_context(SUMMARY, REPOSITORY)
        self.assertEqual("HEI Platform SDK synchronized cache", context["azureDevOps"]["source"])
        self.assertEqual(7, context["azureDevOps"]["workItemRevisions"]["101"])
        self.assertEqual("snapshot-v12", context["repository"]["repositorySnapshotVersion"])
        self.assertEqual("memory-1", context["engineeringMemory"]["matches"][0]["id"])

    def test_existing_epic_selects_modify_instead_of_duplicate_create(self):
        context = self.engine.build_context(SUMMARY, REPOSITORY)
        analysis = self.engine.analyze(context)
        recommendation = self.engine.recommend(context, analysis)
        proposal = self.engine.build_proposal(context, recommendation, {"epic": {"title": SUMMARY["title"], "description": "Expanded approved scope"}})
        epic = proposal["changes"][0]
        self.assertEqual("MODIFY_EXISTING", recommendation["mode"])
        self.assertEqual("Modify", epic["action"])
        self.assertEqual("101", epic["existingWorkItem"]["id"])
        self.assertNotEqual("Create", epic["action"])

    def test_existing_feature_is_kept_and_new_story_is_created(self):
        context = self.engine.build_context(SUMMARY, REPOSITORY)
        recommendation = self.engine.recommend(context, self.engine.analyze(context))
        hierarchy = {
            "epic": {"title": SUMMARY["title"]},
            "features": [{"title": "Device Health Overview", "description": "Current health summary."}],
            "stories": [{"title": "Detect Offline Device Transitions", "feature": "Device Health Overview"}],
        }
        proposal = self.engine.build_proposal(context, recommendation, hierarchy)
        feature = next(item for item in proposal["changes"] if item["artifactType"] == "Feature")
        story = next(item for item in proposal["changes"] if item["title"] == "Detect Offline Device Transitions")
        self.assertIn(feature["action"], {"Keep", "Modify"})
        self.assertEqual("Create", story["action"])

    def test_planning_diff_exposes_field_changes_and_no_change_items(self):
        context = self.engine.build_context(SUMMARY, REPOSITORY)
        recommendation = self.engine.recommend(context, self.engine.analyze(context))
        proposal = self.engine.build_proposal(context, recommendation, {
            "epic": {"title": SUMMARY["title"], "description": "Old scope"},
            "features": [{"title": "Device Health Overview"}],
        })
        diff = self.engine.build_diff(proposal)
        self.assertEqual("Pending", diff["status"])
        self.assertGreaterEqual(diff["summary"]["Keep"], 1)
        self.assertEqual(proposal["sourceRevisions"], diff["sourceRevisions"])

    def test_unrelated_backlog_creates_new_initiative(self):
        engine = IntelligentPlanningEngine(work_item_provider=lambda _project: [
            {"workItemId": 900, "workItemType": "Feature", "title": "Payroll Export", "revision": 1},
        ])
        context = engine.build_context(SUMMARY, REPOSITORY)
        recommendation = engine.recommend(context, engine.analyze(context))
        self.assertEqual("AI_RECOMMENDED", recommendation["mode"])
        proposal = engine.build_proposal(context, recommendation, {})
        self.assertEqual("Create", proposal["changes"][0]["action"])

    def test_requirement_without_prebuilt_hierarchy_proposes_features_and_stories(self):
        context = self.engine.build_context(SUMMARY, REPOSITORY)
        recommendation = self.engine.recommend(context, self.engine.analyze(context))
        proposal = self.engine.build_proposal(context, recommendation, {})
        self.assertTrue(any(item["artifactType"] == "Feature" for item in proposal["changes"]))
        self.assertTrue(any(item["artifactType"] == "Story" for item in proposal["changes"]))
        self.assertTrue(all(item["action"] != "Create" or item["selected"] for item in proposal["changes"]))

    def test_acceptance_criteria_are_grouped_under_an_outcome_story(self):
        summary = {
            **SUMMARY,
            "title": "Offline IoT Device Firmware Update",
            "functionalRequirements": ["Support offline firmware updates for IoT devices."],
            "acceptanceCriteria": [
                "Given a device is connected to a local server, when an update is requested, then the firmware is downloaded.",
                "Given firmware is downloaded, when installation starts, then the update completes without internet access.",
                "Given the update completed, when the device restarts, then the new firmware version is active.",
            ],
        }
        context = self.engine.build_context(summary, REPOSITORY)
        recommendation = self.engine.recommend(context, self.engine.analyze(context))

        proposal = self.engine.build_proposal(context, recommendation, {})
        stories = [item for item in proposal["items"] if item["type"] == "Story"]

        self.assertEqual(1, len(stories))
        self.assertEqual("Support Offline Firmware Updates For Iot Devices", stories[0]["title"])
        self.assertFalse(stories[0]["title"].casefold().startswith(("given ", "when ", "then ")))
        self.assertEqual(summary["acceptanceCriteria"], stories[0]["acceptanceCriteria"])


class PlanningDiffApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = JsonMapStore(Path(self.temp.name) / "planning.json")
        self.record = {
            "requirementId": "req-1", "planningPackId": "pack-1", "correlationId": "corr-1",
            "planningRecommendation": {"mode": "NEW_FEATURE"},
            "planningProposal": {"approval": {"status": "Pending"}},
            "planningDiff": {"status": "Pending", "approval": {"status": "Pending"}, "changes": []},
        }
        self.store.write({"req-1": self.record})
        self.artifact = {"artifact_id": "pack-1", "artifact_type": "PlanningPack", "state": "draft", "version": 1, "payload": {}}
        self.service = RequirementPlanningService(
            self.store, requirement_ingestion=None, requirement_analysis=None, requirement_intake=None,
            estimation_engine=None, artifact_provider=lambda: {"artifacts": [self.artifact]},
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_diff_approval_is_persisted(self):
        result = self.service.approve_diff("pack-1", {"actor": "Product Owner", "comments": "Reviewed"})
        self.assertEqual("Approved", result["diff"]["status"])
        self.assertEqual("Product Owner", result["diff"]["approval"]["approvedBy"])
        self.assertEqual("Approved", self.store.read()["req-1"]["planningProposal"]["approval"]["status"])

    def test_sync_requires_diff_and_planning_pack_approval(self):
        with self.assertRaisesRegex(ValueError, "Planning Diff"):
            self.service.sync("pack-1", {})
        self.service.approve_diff("pack-1", {"actor": "Product Owner"})
        with self.assertRaisesRegex(ValueError, "Planning Pack"):
            self.service.sync("pack-1", {})
        self.artifact.update({"state": "locked", "approved_by": "Product Owner"})
        result = self.service.sync("pack-1", {})
        self.assertEqual("Ready", result["status"])
        self.assertTrue(result["dryRun"])


if __name__ == "__main__":
    unittest.main()
