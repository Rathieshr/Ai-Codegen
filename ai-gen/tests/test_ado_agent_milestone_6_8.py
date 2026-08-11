from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.ado_agent.api import build_ado_agent_router
from backend.ado_agent.models import ActionPackStatus
from backend.ado_agent.policy import AzureDevOpsAgentPolicy
from backend.ado_agent.repository import AzureDevOpsAgentRepository
from backend.ado_agent.service import (
    ActionPackApprovalError, ActionPackConflictError, ActionPackPolicyError,
    AzureDevOpsAgentEventHandler, AzureDevOpsAgentJobHandler, AzureDevOpsAgentService,
)
from backend.governance.policy import PolicyEngine
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


class FakeSdk:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.revisions: dict[str, str] = {"PlanningPack:pack-1": "3", "WorkItem:42": "7", "PullRequest:9": "abc"}
        self.fail_operation = ""

    def analyze_work_item(self, work_item_id, payload, correlation_id):
        self.calls.append(("analyze", work_item_id, correlation_id))
        if self.fail_operation == "AnalyzeWorkItem":
            raise RuntimeError("temporary analysis failure")
        return {"analysisId": "analysis-1", "workItemId": work_item_id, "workItemRevision": 7, "recommendations": []}

    def estimate_work_item(self, work_item_id, payload, correlation_id):
        self.calls.append(("estimate", work_item_id, correlation_id))
        return {"estimateId": "estimate-1", "storyPoints": 5, "dependencies": ["Telemetry"]}

    def analyze_pull_request(self, pull_request_id, payload, correlation_id):
        self.calls.append(("pr", pull_request_id, correlation_id))
        return {"reportId": "pr-report-1", "pullRequestId": pull_request_id, "sourceCommitId": "abc", "readinessStatus": "NeedsReview"}

    def preview_pull_request_comment(self, pull_request_id, payload):
        return {"commentPreviewId": "comment-1", "pullRequestId": pull_request_id, "body": "Review findings"}

    def sprint_report(self, project_id, iteration_id, team_id=""):
        self.calls.append(("sprint", project_id, iteration_id))
        return {"reportId": "sprint-1", "projectId": project_id, "iterationId": iteration_id or "current", "health": "NeedsAttention"}

    def reconcile(self, connection_id, project_id, correlation_id):
        self.calls.append(("reconcile", connection_id, project_id))
        return {"sync": {"status": "Queued"}, "job": {"jobId": "sync-job"}}

    def preview_planning_pack(self, pack_id, payload, correlation_id):
        self.calls.append(("preview-pack", pack_id, correlation_id))
        return {"planId": "plan-1", "sourceRevision": 3, "dryRun": True, "operations": [{"commandType": "CreateFeatureCommand"}]}

    def preview_recommendation(self, recommendation_id, payload, correlation_id):
        self.calls.append(("preview-rec", recommendation_id, correlation_id))
        return {"planId": "plan-2", "sourceRevision": 7, "dryRun": True, "operations": [{"commandType": "UpdateWorkItemCommand"}]}

    def apply(self, operation, source_id, payload, correlation_id):
        self.calls.append(("apply", operation, source_id, payload["idempotencyKey"]))
        if self.fail_operation == operation:
            raise RuntimeError("simulated partial failure")
        return {"status": "Completed", "operation": operation, "sourceId": source_id}

    def current_revision(self, entity, project_id):
        return self.revisions.get(f"{entity.get('type')}:{entity.get('id')}", str(entity.get("revision") or ""))


class DenyPolicy:
    FORBIDDEN = AzureDevOpsAgentPolicy.FORBIDDEN

    def requires_approval(self, operation):
        return True

    def evaluate(self, pack, *, operation, actor=""):
        return {"allowed": False, "status": "Blocked", "violations": [{"message": "Organization policy denied this action."}], "warnings": []}


class AzureDevOpsAgentMilestone68Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.platform = PlatformFoundation(root / "platform")
        self.repository = AzureDevOpsAgentRepository(JsonMapStore(root / "packs.json"), JsonMapStore(root / "receipts.json"))
        self.sdk = FakeSdk()
        self.policy = AzureDevOpsAgentPolicy(PolicyEngine())
        self.service = AzureDevOpsAgentService(repository=self.repository, sdk=self.sdk, policy=self.policy, platform=self.platform, ttl_minutes=60)
        self.platform.job_handlers.register("AzureDevOpsAgent", AzureDevOpsAgentJobHandler(self.service, self.platform))
        self.handler = AzureDevOpsAgentEventHandler(self.repository, self.platform)
        for event in ("PlanningPackApproved", "WorkItemUpdated", "PullRequestCreated"):
            self.platform.event_handlers.subscribe(event, self.handler)
        self.payload = {"connectionId": "conn-1", "projectId": "Project", "planningPackId": "pack-1"}

    def tearDown(self):
        self.temp.cleanup()

    def _prepared_pack(self, **extra):
        return self.service.prepare("PlanningPackApproved", {**self.payload, **extra}, correlation_id="corr-pack")

    def test_event_trigger_queues_job_and_agent_runtime_prepares_pack(self):
        event = self.platform.events.publish({"eventId": "event-1", "eventType": "PlanningPackApproved", "projectId": "Project", "correlationId": "corr-event", "payload": self.payload})
        self.assertEqual("event-1", event["eventId"])
        result = self.platform.job_runner.run_next()
        self.assertTrue(result["success"])
        packs = self.service.list_packs()["actionPacks"]
        self.assertEqual(1, len(packs))
        self.assertEqual(ActionPackStatus.PENDING_APPROVAL.value, packs[0]["approvalStatus"])
        self.assertEqual(1, self.service.list_runs()["count"])

    def test_preparation_does_not_apply_without_approval(self):
        pack = self._prepared_pack()
        self.assertFalse(any(call[0] == "apply" for call in self.sdk.calls))
        with self.assertRaises(ActionPackApprovalError):
            self.service.apply(pack["packId"], "release-manager")

    def test_approved_pack_applies_bounded_action(self):
        pack = self._prepared_pack()
        self.service.approve(pack["packId"], "product-owner")
        applied = self.service.apply(pack["packId"], "release-manager", idempotency_key="apply-1")
        self.assertEqual(ActionPackStatus.APPLIED.value, applied["approvalStatus"])
        self.assertIn(("apply", "ApplyPlanningPack", "pack-1", "apply-1"), self.sdk.calls)

    def test_structured_automation_failure_does_not_mark_pack_applied(self):
        pack = self._prepared_pack()
        self.service.approve(pack["packId"], "product-owner")
        original_apply = self.sdk.apply
        self.sdk.apply = lambda *_args, **_kwargs: {
            "status": "Failed",
            "failure": {"message": "Azure DevOps rejected the work-item create request."},
            "externalIds": {},
        }
        try:
            result = self.service.apply(pack["packId"], "release-manager", idempotency_key="apply-failed")
        finally:
            self.sdk.apply = original_apply
        self.assertEqual(ActionPackStatus.FAILED.value, result["approvalStatus"])
        self.assertEqual("Failed", result["applicationResults"][0]["status"])
        self.assertIn("rejected", result["applicationResults"][0]["error"])

    def test_expired_approval_is_rejected(self):
        pack = self.repository.get(self._prepared_pack()["packId"])
        pack.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.repository.save(pack)
        with self.assertRaises(ActionPackApprovalError):
            self.service.approve(pack.pack_id, "product-owner")
        self.assertEqual(ActionPackStatus.EXPIRED.value, self.repository.get(pack.pack_id).approval_status)

    def test_stale_source_revision_blocks_approval(self):
        pack = self._prepared_pack()
        self.sdk.revisions["PlanningPack:pack-1"] = "4"
        with self.assertRaises(ActionPackConflictError):
            self.service.approve(pack["packId"], "product-owner")
        self.assertEqual(ActionPackStatus.STALE.value, self.repository.get(pack["packId"]).approval_status)

    def test_rejected_pack_cannot_be_applied(self):
        pack = self._prepared_pack()
        rejected = self.service.reject(pack["packId"], "product-owner", reason="Scope changed")
        self.assertEqual(ActionPackStatus.REJECTED.value, rejected["approvalStatus"])
        with self.assertRaises(ActionPackApprovalError):
            self.service.apply(pack["packId"], "release-manager")

    def test_policy_denial_blocks_pack_approval(self):
        service = AzureDevOpsAgentService(repository=self.repository, sdk=self.sdk, policy=DenyPolicy(), platform=self.platform)
        pack = service.prepare("PlanningPackApproved", self.payload, correlation_id="corr-policy")
        self.assertEqual(ActionPackStatus.POLICY_DENIED.value, pack["approvalStatus"])
        with self.assertRaises(ActionPackApprovalError):
            service.approve(pack["packId"], "product-owner")

    def test_partial_failure_preserves_successful_action_results(self):
        pack = self._prepared_pack(recommendationId="rec-1")
        self.service.approve(pack["packId"], "product-owner")
        self.sdk.fail_operation = "ApplyRecommendation"
        result = self.service.apply(pack["packId"], "release-manager")
        self.assertEqual(ActionPackStatus.PARTIAL.value, result["approvalStatus"])
        self.assertEqual(["Completed", "Failed"], [item["status"] for item in result["applicationResults"]])

    def test_partial_failure_can_resume_without_reapplying_completed_action(self):
        pack = self._prepared_pack(recommendationId="rec-1")
        self.service.approve(pack["packId"], "product-owner")
        self.sdk.fail_operation = "ApplyRecommendation"
        self.service.apply(pack["packId"], "release-manager")
        planning_apply_count = len([call for call in self.sdk.calls if call[:2] == ("apply", "ApplyPlanningPack")])
        self.sdk.fail_operation = ""
        resumed = self.service.apply(pack["packId"], "release-manager")
        self.assertEqual(ActionPackStatus.APPLIED.value, resumed["approvalStatus"])
        self.assertEqual(planning_apply_count, len([call for call in self.sdk.calls if call[:2] == ("apply", "ApplyPlanningPack")]))

    def test_failed_agent_job_is_queued_for_retry(self):
        self.sdk.fail_operation = "AnalyzeWorkItem"
        self.platform.events.publish({"eventId": "retry-event", "eventType": "WorkItemUpdated", "projectId": "Project", "workItemId": "42", "correlationId": "corr-retry", "payload": {"projectId": "Project", "workItemId": "42"}})
        result = self.platform.job_runner.run_next()
        self.assertFalse(result["success"])
        self.assertEqual("Queued", result["metadata"]["job"]["status"])
        self.assertEqual(1, result["metadata"]["job"]["retryCount"])

    def test_duplicate_event_is_idempotent(self):
        event = {"eventId": "duplicate-1", "eventType": "PlanningPackApproved", "projectId": "Project", "correlationId": "corr-duplicate", "payload": self.payload}
        self.platform.events.publish(event)
        self.platform.events.publish(event)
        self.assertEqual(1, self.platform.jobs.list_recent()["count"])

    def test_approval_and_apply_are_audited_with_same_correlation(self):
        pack = self._prepared_pack()
        self.service.approve(pack["packId"], "product-owner")
        self.service.apply(pack["packId"], "release-manager")
        audit = self.platform.audit.by_correlation("corr-pack")["events"]
        self.assertEqual({"AzureDevOpsActionPackApproved", "AzureDevOpsActionPackApplied"}, {item["action"] for item in audit})

    def test_manual_forbidden_action_is_policy_denied_and_never_executed(self):
        pack = self.service.prepare("ManualRequest", {"requestedActions": ["MergePullRequest"]}, correlation_id="corr-forbidden")
        self.assertEqual(ActionPackStatus.POLICY_DENIED.value, pack["approvalStatus"])
        self.assertFalse(any(call[0] == "apply" for call in self.sdk.calls))

    def test_api_exposes_only_requested_run_and_action_pack_routes(self):
        paths = {route.path for route in build_ado_agent_router(self.service).routes}
        self.assertEqual({
            "/ado-agent/runs", "/ado-agent/runs/{run_id}",
            "/ado-agent/action-packs", "/ado-agent/action-packs/{pack_id}",
            "/ado-agent/action-packs/{pack_id}/approve", "/ado-agent/action-packs/{pack_id}/reject",
            "/ado-agent/action-packs/{pack_id}/apply",
        }, paths)


if __name__ == "__main__":
    unittest.main()
