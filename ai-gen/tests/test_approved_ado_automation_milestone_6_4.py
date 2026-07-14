from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.ado_intelligence.models import RecommendationStatus, WorkItemRecommendation
from backend.ado_intelligence.repository import WorkItemRecommendationRepository
from backend.integrations.azure_devops.automation.api import build_ado_automation_router
from backend.integrations.azure_devops.automation.service import (
    AutomationApprovalError, AutomationConflictError, AutomationPermissionError,
    AzureDevOpsAutomationService,
)
from backend.integrations.azure_devops.automation.store import AutomationExecutionStore
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


class FakeReadClient:
    def __init__(self) -> None:
        self.items = {42: {"id": 42, "rev": 7, "fields": {"System.Title": "Current"}}}

    def get_work_item(self, project: str, work_item_id: int):
        return dict(self.items[work_item_id])


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.next_id = 1000
        self.fail_at: int | None = None

    def _check(self) -> None:
        if self.fail_at and len(self.calls) == self.fail_at:
            self.fail_at = None
            raise RuntimeError("simulated write failure")

    def create_work_item(self, project, work_item_type, fields):
        self.calls.append(("create", work_item_type, dict(fields)))
        self._check()
        self.next_id += 1
        return {"id": self.next_id, "rev": 1, "fields": fields}

    def update_work_item(self, project, work_item_id, fields, *, expected_revision):
        self.calls.append(("update", work_item_id, dict(fields), expected_revision))
        self._check()
        return {"id": work_item_id, "rev": expected_revision + 1, "fields": fields}

    def link_parent_child(self, project, parent_id, child_id, *, expected_revision):
        self.calls.append(("link", parent_id, child_id, expected_revision))
        self._check()
        return {"id": child_id, "rev": expected_revision + 1}

    def add_comment(self, project, work_item_id, comment):
        self.calls.append(("comment", work_item_id, comment))
        self._check()
        return {"id": work_item_id, "rev": 1, "comment": comment}


class FakeConnections:
    def __init__(self, reader, writer, *, permissions=None) -> None:
        self.reader = reader
        self.write_client = writer
        self.connection = {"connectionId": "conn-1", "projectId": "Project", "status": "Connected", "permissions": permissions if permissions is not None else ["WorkItems.Write"]}

    def get(self, connection_id):
        return dict(self.connection) if connection_id == "conn-1" else None

    def client(self, connection_id, correlation_id=""):
        return self.reader

    def writer(self, connection_id, correlation_id=""):
        return self.write_client


class ApprovedAzureDevOpsAutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.platform = PlatformFoundation(root / "platform")
        self.recommendations = WorkItemRecommendationRepository(JsonMapStore(root / "recommendations.json"), JsonMapStore(root / "analyses.json"))
        self.reader = FakeReadClient()
        self.writer = FakeWriter()
        self.connections = FakeConnections(self.reader, self.writer)
        self.packs: dict[str, dict] = {}
        self.service = AzureDevOpsAutomationService(
            azure_devops=SimpleNamespace(connections=self.connections),
            recommendations=self.recommendations,
            execution_store=AutomationExecutionStore(JsonMapStore(root / "executions.json")),
            planning_pack_provider=self.packs.get,
            platform=self.platform,
        )
        self.request = {"connectionId": "conn-1", "projectId": "Project", "idempotencyKey": "request-1", "executor": "release-manager", "reason": "Approved delivery plan"}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _recommendation(self, *, status=RecommendationStatus.APPROVED, revision=7, kind="NormalizedTitle", proposed="Proposed") -> WorkItemRecommendation:
        item = WorkItemRecommendation("rec-1", "42", revision, kind, "Current", proposed, ["Approved improvement"], [], 0.92, status=status, approved_by="product-owner" if status == RecommendationStatus.APPROVED else "", project_id="Project")
        self.recommendations.save(item)
        return item

    def _pack(self, items: list[dict]) -> dict:
        pack = {"artifact_id": "pack-1", "artifact_type": "PlanningPack", "state": "locked", "approved_by": "product-owner", "version": 3, "payload": {"items": items}}
        self.packs["pack-1"] = pack
        return pack

    def test_dry_run_lists_operations_without_writing(self):
        self._recommendation()
        result = self.service.preview_recommendation("rec-1", self.request, correlation_id="corr-preview")
        self.assertTrue(result["dryRun"])
        self.assertEqual("UpdateWorkItemCommand", result["operations"][0]["commandType"])
        self.assertEqual([], self.writer.calls)
        self.assertEqual(7, result["currentValues"]["42"]["revision"])

    def test_approved_epic_creation(self):
        self._pack([{"alias": "epic", "type": "Epic", "title": "Device Health"}])
        result = self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-epic")
        self.assertEqual("Completed", result["status"])
        self.assertTrue(result["externalIds"]["epic"].isdigit())
        self.assertEqual("Epic", self.writer.calls[0][1])

    def test_complete_hierarchy_creation(self):
        self._pack([
            {"alias": "epic", "type": "Epic", "title": "Device Health"},
            {"alias": "feature", "type": "Feature", "title": "Health Overview", "parentAlias": "epic"},
            {"alias": "story", "type": "Story", "title": "View Health", "parentAlias": "feature"},
            {"alias": "task", "type": "Task", "title": "Build query", "parentAlias": "story"},
        ])
        result = self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-tree")
        self.assertEqual("Completed", result["status"])
        self.assertEqual(4, len([call for call in self.writer.calls if call[0] == "create"]))
        self.assertEqual(3, len([call for call in self.writer.calls if call[0] == "link"]))

    def test_duplicate_retry_reuses_external_ids(self):
        self._pack([{"alias": "epic", "type": "Epic", "title": "Device Health"}])
        first = self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-first")
        call_count = len(self.writer.calls)
        second = self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-second")
        self.assertTrue(second["idempotentReplay"])
        self.assertEqual(first["externalIds"], second["externalIds"])
        self.assertEqual(call_count, len(self.writer.calls))

    def test_applied_recommendation_retry_is_idempotent(self):
        self._recommendation()
        first = self.service.apply_recommendation("rec-1", self.request, correlation_id="corr-rec-first")
        call_count = len(self.writer.calls)
        second = self.service.apply_recommendation("rec-1", self.request, correlation_id="corr-rec-retry")
        self.assertEqual(first["executionId"], second["executionId"])
        self.assertTrue(second["idempotentReplay"])
        self.assertEqual(call_count, len(self.writer.calls))

    def test_permission_failure_blocks_write(self):
        self._recommendation()
        self.connections.connection["permissions"] = ["WorkItems.Read"]
        preview = self.service.preview_recommendation("rec-1", self.request, correlation_id="corr-permission-preview")
        self.assertIn("WorkItems.Write", " ".join(preview["warnings"]))
        with self.assertRaises(AutomationPermissionError):
            self.service.apply_recommendation("rec-1", self.request, correlation_id="corr-permission")
        self.assertEqual([], self.writer.calls)
        events = self.platform.audit.by_correlation("corr-permission")["events"]
        self.assertEqual(["AzureDevOpsAutomationDenied"], [event["action"] for event in events])

    def test_stale_revision_marks_recommendation_stale(self):
        self._recommendation(revision=6)
        with self.assertRaises(AutomationConflictError):
            self.service.apply_recommendation("rec-1", self.request, correlation_id="corr-stale")
        self.assertEqual(RecommendationStatus.STALE, self.recommendations.get("rec-1").status)
        self.assertEqual([], self.writer.calls)

    def test_partial_failure_is_persisted(self):
        self._pack([{"alias": "epic", "type": "Epic", "title": "A"}, {"alias": "feature", "type": "Feature", "title": "B", "parentAlias": "epic"}])
        self.writer.fail_at = 2
        result = self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-partial")
        self.assertEqual("Partial", result["status"])
        self.assertIn("epic", result["externalIds"])
        self.assertIsNotNone(result["failure"])

    def test_retry_after_partial_failure_does_not_duplicate_parent(self):
        self._pack([{"alias": "epic", "type": "Epic", "title": "A"}, {"alias": "feature", "type": "Feature", "title": "B", "parentAlias": "epic"}])
        self.writer.fail_at = 2
        self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-partial")
        result = self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-resume")
        self.assertEqual("Completed", result["status"])
        self.assertEqual(1, len([call for call in self.writer.calls if call[:2] == ("create", "Epic")]))

    def test_parent_child_link_uses_created_external_ids(self):
        self._pack([{"alias": "epic", "type": "Epic", "title": "A"}, {"alias": "feature", "type": "Feature", "title": "B", "parentAlias": "epic"}])
        result = self.service.apply_planning_pack("pack-1", self.request, correlation_id="corr-link")
        link = next(call for call in self.writer.calls if call[0] == "link")
        self.assertEqual(int(result["externalIds"]["epic"]), link[1])
        self.assertEqual(int(result["externalIds"]["feature"]), link[2])

    def test_story_point_write_uses_explicit_command(self):
        self._recommendation(kind="StoryPointRecommendation", proposed={"points": 8})
        result = self.service.apply_recommendation("rec-1", self.request, correlation_id="corr-points")
        self.assertEqual("Completed", result["status"])
        self.assertEqual(8, self.writer.calls[0][2]["Microsoft.VSTS.Scheduling.StoryPoints"])

    def test_audit_trace_records_authorization_and_result(self):
        self._recommendation()
        self.service.apply_recommendation("rec-1", self.request, correlation_id="corr-audit")
        audit = self.platform.audit.by_correlation("corr-audit")["events"]
        self.assertEqual(2, len(audit))
        self.assertEqual({"AzureDevOpsAutomationAuthorized", "AzureDevOpsAutomationApplied"}, {item["action"] for item in audit})
        self.assertTrue(all(item["actor"] == "release-manager" for item in audit))

    def test_unapproved_source_and_unrestricted_routes_are_rejected(self):
        self._recommendation(status=RecommendationStatus.NEEDS_REVIEW)
        with self.assertRaises(AutomationApprovalError):
            self.service.preview_recommendation("rec-1", self.request, correlation_id="corr-denied")
        paths = {route.path for route in build_ado_automation_router(self.service).routes}
        self.assertEqual({
            "/ado-automation/planning-packs/{planning_pack_id}/preview",
            "/ado-automation/planning-packs/{planning_pack_id}/apply",
            "/ado-automation/recommendations/{recommendation_id}/preview",
            "/ado-automation/recommendations/{recommendation_id}/apply",
        }, paths)


if __name__ == "__main__":
    unittest.main()
