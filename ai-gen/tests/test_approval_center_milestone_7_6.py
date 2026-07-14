from __future__ import annotations

import unittest

from backend.approval_center.api import build_approval_center_router
from backend.approval_center.service import ApprovalCenterService, ApprovalConflictError, ApprovalPermissionError


class ApprovalCenterMilestone76Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.decisions: list[tuple] = []
        self.audit: list[dict] = []
        self.governance: list[dict] = [{
            "id": "gov-validation", "artifactType": "Validation Exception", "artifactId": "exception-1",
            "artifactTitle": "Permission test exception", "status": "Pending", "createdAt": "2026-07-14T09:00:00Z",
        }]
        self.service = ApprovalCenterService(
            planning_provider=lambda: {"items": [{"id": "pack-1", "type": "Story", "title": "Device health planning pack", "source": "planning_artifact", "status": "Draft", "approvalStatus": "Pending", "updatedAt": "2026-07-14T10:00:00Z"}]},
            planning_approve=lambda item_id, actor: self._decision("planning-approve", item_id, actor),
            planning_reject=lambda item_id, actor: self._decision("planning-reject", item_id, actor),
            execution_plan_provider=lambda: {"manifest-1": {"manifestId": "manifest-1", "objective": "Implement device health", "generatedAt": "2026-07-14T08:00:00Z"}},
            memory_provider=lambda: {"candidates": [{"candidateId": "memory-1", "candidateType": "Reusable Pattern", "approvalStatus": "Pending", "createdAt": "2026-07-14T07:00:00Z"}]},
            memory_approve=lambda item_id, actor: self._decision("memory-approve", item_id, actor),
            memory_reject=lambda item_id, actor, reason: self._decision("memory-reject", item_id, actor, reason),
            ado_pack_provider=lambda: {"actionPacks": [{"packId": "ado-1", "trigger": "PlanningPackApproved", "approvalStatus": "PendingApproval", "expiresAt": "2099-01-01T00:00:00Z", "createdAt": "2026-07-14T06:00:00Z"}]},
            ado_pack_approve=lambda item_id, actor, reason: self._decision("ado-approve", item_id, actor, reason),
            ado_pack_reject=lambda item_id, actor, reason: self._decision("ado-reject", item_id, actor, reason),
            pr_comment_provider=lambda: {"comment-1": {"commentPreviewId": "comment-1", "pullRequestId": "42", "approvalStatus": "PendingApproval", "content": "Review comment", "createdAt": "2026-07-14T05:00:00Z"}},
            pr_comment_approve=lambda item_id, actor, reason: self._decision("comment-approve", item_id, actor, reason),
            pr_comment_reject=lambda item_id, actor, reason: self._decision("comment-reject", item_id, actor, reason),
            recommendation_provider=lambda: [{"recommendationId": "rec-1", "recommendationType": "Title", "proposedValue": "Improve title", "status": "NeedsReview", "createdAt": "2026-07-14T04:00:00Z"}],
            recommendation_approve=lambda item_id, actor: self._decision("recommendation-approve", item_id, actor),
            recommendation_reject=lambda item_id, actor: self._decision("recommendation-reject", item_id, actor),
            governance_provider=lambda: {"approvals": self.governance},
            governance_request=self._governance_request,
            governance_update=lambda item_id, status, actor, reason: self._decision("governance", item_id, status, actor, reason),
            audit_provider=lambda source_id: {"events": [item for item in self.audit if item.get("artifactId") == source_id]},
            audit_recorder=self._audit,
        )

    def _decision(self, *args):
        self.decisions.append(args)
        return {"decision": args}

    def _audit(self, event):
        self.audit.append(event)
        return {"event": event}

    def _governance_request(self, approval, actor):
        value = {**approval, "id": f"gov-{approval['artifactId']}", "requestedBy": actor}
        self.governance.append(value)
        return {"approval": value}

    def test_multiple_approval_types_share_one_queue(self):
        result = self.service.list(limit=250)
        self.assertEqual(result["summary"]["total"], 7)
        self.assertEqual(set(result["summary"]["byCategory"]), {
            "Planning Packs", "Execution Plans", "Memory Candidates", "ADO Action Packs",
            "PR Comments", "Validation Exceptions", "Recommendations",
        })

    def test_expired_approval_cannot_be_approved(self):
        service = ApprovalCenterService(
            ado_pack_provider=lambda: {"actionPacks": [{"packId": "expired", "trigger": "ManualRequest", "approvalStatus": "PendingApproval", "expiresAt": "2020-01-01T00:00:00Z"}]},
            ado_pack_approve=lambda *_args: self.fail("expired operation must not be delegated"),
        )
        item = service.list()["approvals"][0]
        self.assertEqual(item["status"], "Expired")
        with self.assertRaises(ApprovalConflictError):
            service.approve(item["id"], "Admin", "admin")

    def test_viewer_cannot_make_decisions(self):
        with self.assertRaises(ApprovalPermissionError):
            self.service.approve("planning-packs:pack-1", "Reader", "viewer")
        with self.assertRaises(ApprovalPermissionError):
            self.service.approve("planning-packs:pack-1", "Unknown", "custom-role")
        self.assertEqual(self.decisions, [])

    def test_decision_delegates_and_records_audit(self):
        result = self.service.approve("memory-candidates:memory-1", "Reviewer", "contributor", "Reusable pattern verified")
        self.assertEqual(result["approval"]["status"], "Approved")
        self.assertEqual(self.decisions[0][:3], ("memory-approve", "memory-1", "Reviewer"))
        detail = self.service.get("memory-candidates:memory-1")
        self.assertEqual(len(detail["audit"]), 1)
        self.assertEqual(detail["audit"][0]["eventType"], "ApprovalCenterDecision")

    def test_execution_plan_uses_governance_approval(self):
        self.service.reject("execution-plans:manifest-1", "Lead", "admin", "Boundary requires revision")
        self.assertEqual(self.decisions[-1][0], "governance")
        self.assertEqual(self.decisions[-1][2], "Rejected")

    def test_routes_expose_required_contract(self):
        paths = {(route.path, tuple(sorted(route.methods or []))) for route in build_approval_center_router(self.service).routes}
        self.assertIn(("/approvals", ("GET",)), paths)
        self.assertIn(("/approvals/{approval_id}", ("GET",)), paths)
        self.assertIn(("/approvals/{approval_id}/approve", ("POST",)), paths)
        self.assertIn(("/approvals/{approval_id}/reject", ("POST",)), paths)


if __name__ == "__main__":
    unittest.main()
