from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.engineering_review import EngineeringReviewService, build_engineering_review_router
from backend.approval_center import ApprovalCenterService
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


def proposal() -> dict:
    story_id = "story-1"
    return {
        "proposalId": "proposal-1",
        "title": "Device Health Planning",
        "executiveSummary": "Add a repository-aligned device health experience.",
        "version": 3,
        "status": "Review",
        "contextId": "context-1",
        "contextVersion": "context-v4",
        "knowledgeVersion": "knowledge-v7",
        "recommendationVersion": 2,
        "correlationId": "corr-review",
        "validation": {"status": "Approved", "mandatoryPassed": True, "findings": []},
        "health": {"risk": "Medium", "overallHealth": 91},
        "estimate": {"engineeringDays": 18, "storyPoints": 34},
        "acceptanceCriteria": [
            {"criterionId": "ac-1", "text": "Operator can view unhealthy devices.", "status": "Approved"},
        ],
        "nodes": [
            {
                "nodeId": "epic-1", "type": "Epic", "title": "Device Health",
                "status": "Draft", "parentId": "", "owner": "Platform Team",
                "repositoryMapping": {"repositoryName": "GridHub"},
            },
            {
                "nodeId": "feature-1", "type": "Feature", "title": "Health Overview",
                "status": "Draft", "parentId": "epic-1", "owner": "Platform Team",
                "repositoryMapping": {"repositoryName": "GridHub"},
            },
            {
                "nodeId": story_id, "type": "Story", "title": "View Device Health",
                "status": "Draft", "parentId": "feature-1", "owner": "Platform Team",
                "acceptanceCriteria": ["Operator can view unhealthy devices."],
                "repositoryMapping": {"repositoryName": "GridHub"},
            },
            {
                "nodeId": "task-1", "type": "Task", "title": "Implement health query",
                "status": "Draft", "parentId": story_id, "owner": "API Team",
                "repositoryMapping": {"repositoryName": "GridHub"},
            },
        ],
        "dependencies": [],
        "dependencyGraph": {
            "categories": {
                "crossTeamDependencies": [{"team": "API Team"}],
            },
        },
    }


class EngineeringReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.proposals = {"proposal-1": proposal()}
        self.platform = PlatformFoundation(self.root / "platform")

        def approve(proposal_id: str, actor: str, comments: str):
            value = self.proposals[proposal_id]
            value["status"] = "Approved"
            value["approvedBy"] = actor
            value["approvedAt"] = "2026-07-24T10:00:00Z"
            value["approvalComments"] = comments
            for node in value["nodes"]:
                node["status"] = "Approved"
            return value

        self.service = EngineeringReviewService(
            JsonMapStore(self.root / "reviews.json"),
            proposal_provider=lambda proposal_id: self.proposals[proposal_id],
            proposal_approver=approve,
            platform=self.platform,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_dashboard_contains_versioned_summary_and_single_approval(self):
        review = self.service.create({"proposalId": "proposal-1", "owner": "Owner"})
        self.assertEqual(1, len(review["stages"]))
        self.assertEqual("Planning Approver", review["currentStage"]["role"])
        self.assertEqual("Single", review["approvalMode"])
        self.assertEqual("context-v4", review["contextVersion"])
        self.assertEqual("knowledge-v7", review["knowledgeVersion"])
        self.assertEqual(2, review["recommendationVersion"])
        self.assertEqual(["GridHub"], review["affectedRepositories"])
        self.assertEqual({"Platform Team", "API Team"}, set(review["affectedTeams"]))

    def test_inline_comments_and_change_requests_are_versioned_and_searchable(self):
        review = self.service.create({"proposalId": "proposal-1", "owner": "Owner"})
        review = self.service.comment(review["reviewId"], {
            "targetType": "Story", "targetId": "story-1",
            "section": "Acceptance Criteria Review",
            "comment": "Clarify the stale-device threshold.", "actor": "Product Owner",
        })
        self.assertEqual(1, review["sections"][3]["commentCount"])
        review = self.service.request_change(review["reviewId"], {
            "changeType": "Acceptance Criteria Update",
            "description": "Add the stale-device threshold.", "targetId": "story-1",
            "actor": "Product Owner",
        })
        self.assertFalse(review["readiness"]["approvalAllowed"])
        self.assertIn("Open change requests must be resolved.", review["readiness"]["blockers"])
        change = review["changeRequests"][0]
        review = self.service.resolve_change(review["reviewId"], change["changeRequestId"], {
            "actor": "Proposal Owner", "resolution": "Threshold added to AC-1.",
        })
        self.assertTrue(review["readiness"]["approvalAllowed"])
        history = self.service.history(review["reviewId"], search="threshold")
        self.assertGreaterEqual(history["count"], 2)

    def test_configured_roles_approve_in_order_and_final_stage_freezes_proposal(self):
        approval_chain = [
            {"stageId": role.casefold().replace(" ", "-"), "name": role, "role": role, "order": index}
            for index, role in enumerate(("Product Owner", "Engineering Lead", "Architect", "QA Lead", "Delivery Manager"), 1)
        ]
        review = self.service.create({"proposalId": "proposal-1", "owner": "Owner", "approvalChain": approval_chain})
        for role in ("Product Owner", "Engineering Lead", "Architect", "QA Lead", "Delivery Manager"):
            review = self.service.decide(review["reviewId"], {
                "decision": "Approve",
                "actor": f"{role} Reviewer",
                "role": role,
            })
        self.assertEqual("Approved", review["status"])
        self.assertEqual("Approved", self.proposals["proposal-1"]["status"])
        self.assertTrue(review["synchronization"]["authorized"])
        self.assertTrue(review["readiness"]["checks"]["architectureApproved"])
        self.assertTrue(review["readiness"]["checks"]["riskAccepted"])
        with self.assertRaises(ValueError):
            self.service.comment(review["reviewId"], {
                "targetType": "Epic", "comment": "Too late", "actor": "Reviewer",
            })

    def test_wrong_role_and_missing_comments_are_rejected(self):
        review = self.service.create({"proposalId": "proposal-1", "owner": "Owner"})
        with self.assertRaises(PermissionError):
            self.service.decide(review["reviewId"], {
                "decision": "Approve", "actor": "Engineer", "role": "Engineering Lead",
            })
        with self.assertRaises(ValueError):
            self.service.decide(review["reviewId"], {
                "decision": "Reject", "actor": "Planning Approver", "role": "Planning Approver",
            })

    def test_pending_multi_stage_review_is_migrated_to_single_approval(self):
        values = {
            "review-existing": {
                "reviewId": "review-existing", "proposalId": "proposal-1", "proposalVersion": 3,
                "status": "InReview", "currentStageId": "architect", "stages": [
                    {"stageId": "engineering-lead", "role": "Engineering Lead", "status": "Approved", "order": 1},
                    {"stageId": "architect", "role": "Architect", "status": "Pending", "order": 2},
                ],
            },
        }
        store = JsonMapStore(self.root / "migration-reviews.json")
        store.write(values)
        EngineeringReviewService(
            store,
            proposal_provider=lambda proposal_id: self.proposals[proposal_id],
            proposal_approver=lambda proposal_id, actor, comments: self.proposals[proposal_id],
        )
        migrated = store.read()["review-existing"]
        self.assertEqual("Single", migrated["approvalMode"])
        self.assertEqual("PendingReview", migrated["status"])
        self.assertEqual("Planning Approver", migrated["stages"][0]["role"])

    def test_proposal_version_change_supersedes_review_and_blocks_sync(self):
        review = self.service.create({"proposalId": "proposal-1", "owner": "Owner"})
        self.proposals["proposal-1"]["version"] = 4
        self.proposals["proposal-1"]["status"] = "Draft"
        self.service.invalidate("proposal-1", 4, "Editor")
        current = self.service.get(review["reviewId"])
        self.assertEqual("Superseded", current["status"])
        authorization = self.service.authorize_synchronization("proposal-1")
        self.assertFalse(authorization["authorized"])
        self.assertTrue(any("not approved" in reason for reason in authorization["reasons"]))

    def test_reports_notifications_audit_and_api_contract(self):
        review = self.service.create({"proposalId": "proposal-1", "owner": "Owner"})
        report = self.service.report(review["reviewId"], "Architecture Summary")
        self.assertEqual("Markdown", report["format"])
        self.assertIn("# Architecture Summary", report["content"])
        pdf = self.service.report(review["reviewId"], "Approval Report", "PDF")
        self.assertEqual("PDF", pdf["format"])
        self.assertTrue(pdf["contentBase64"].startswith("JVBER"))
        self.assertGreater(self.platform.notifications.list_recent()["count"], 0)
        self.assertGreater(self.platform.audit.by_target("EngineeringReview", review["reviewId"])["count"], 0)

        app = FastAPI()
        app.include_router(build_engineering_review_router(self.service))
        client = TestClient(app)
        self.assertEqual(200, client.get(f"/engineering-reviews/{review['reviewId']}").status_code)
        self.assertEqual(200, client.get("/engineering-reviews").status_code)
        self.assertEqual(
            200,
            client.get(f"/engineering-reviews/proposal/proposal-1/synchronization-authorization").status_code,
        )
        paths = {route.path for route in build_engineering_review_router(self.service).routes}
        for path in (
            "/engineering-reviews/{review_id}/assign",
            "/engineering-reviews/{review_id}/comments",
            "/engineering-reviews/{review_id}/change-requests",
            "/engineering-reviews/{review_id}/decision",
            "/engineering-reviews/{review_id}/history",
            "/engineering-reviews/{review_id}/report",
        ):
            self.assertIn(path, paths)

    def test_review_is_actionable_through_shared_approval_center(self):
        review = self.service.create({"proposalId": "proposal-1", "owner": "Owner"})
        center = ApprovalCenterService(
            engineering_review_provider=self.service.list,
            engineering_review_decide=self.service.decide,
        )
        item = center.list(category="Engineering Reviews")["approvals"][0]
        self.assertEqual("NeedsReview", item["status"])
        self.assertTrue(item["canApprove"])
        decided = center.approve(
            item["id"], "Product Reviewer", "contributor", "Business scope approved."
        )
        self.assertEqual("Approved", decided["sourceResult"]["status"])
        self.assertEqual({}, decided["sourceResult"]["currentStage"])


if __name__ == "__main__":
    unittest.main()
