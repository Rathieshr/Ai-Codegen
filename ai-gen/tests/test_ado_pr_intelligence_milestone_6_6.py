from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_intelligence.api import build_ado_intelligence_router
from backend.ado_intelligence.pr_repository import PullRequestIntelligenceRepository
from backend.ado_intelligence.pr_service import PullRequestIntelligenceService
from backend.integrations.azure_devops.application.services import AzureDevOpsPullRequestService
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


class Cache:
    def __init__(self) -> None:
        self.values = {}

    def find(self, collection, key, project_id=""):
        if project_id and (project_id, collection, str(key)) in self.values:
            return project_id, self.values[(project_id, collection, str(key))]
        return next(((project, value) for (project, name, item_id), value in self.values.items() if name == collection and item_id == str(key)), None)

    def upsert(self, project_id, collection, key, value, **_kwargs):
        self.values[(project_id, collection, str(key))] = value
        return "created"


class CommentWriter:
    def __init__(self) -> None:
        self.calls = []

    def add_comment(self, project_id, repository_id, pull_request_id, content):
        self.calls.append((project_id, repository_id, pull_request_id, content))
        return {"id": 91}


class Connections:
    def __init__(self, writer) -> None:
        self.writer = writer

    def get(self, _connection_id):
        return {"connectionId": "ado-1", "permissions": ["PullRequests.Contribute"]}

    def pull_request_comment_writer(self, _connection_id, _correlation_id=""):
        return self.writer


class PullRequests:
    def get_pull_request_context(self, *_args, **_kwargs):
        raise AssertionError("Tests use synchronized or supplied PR context.")


class DetailedReadClient:
    def get_pull_request(self, *_args, **_kwargs):
        return {"pullRequestId": 17, "title": "Fault details", "status": "active", "repository": {"id": "repo-1"}}

    def get_pull_request_commits(self, *_args, **_kwargs):
        return [{"commitId": "commit-2"}]

    def get_pull_request_work_items(self, *_args, **_kwargs):
        return [{"id": 42}]

    def get_pull_request_iterations(self, *_args, **_kwargs):
        return [{"id": 3}]

    def get_pull_request_iteration_changes(self, *_args, **_kwargs):
        return [{"changeType": "edit", "item": {"path": "/src/fault_details.py", "objectId": "obj-2"}}]


class ReadConnections:
    def client(self, *_args, **_kwargs):
        return DetailedReadClient()


class PullRequestIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.platform = PlatformFoundation(root / "platform")
        self.cache = Cache()
        self.writer = CommentWriter()
        self.azure = SimpleNamespace(
            sync=SimpleNamespace(cache=self.cache),
            connections=Connections(self.writer),
            pull_requests=PullRequests(),
        )
        repository = PullRequestIntelligenceRepository(
            JsonMapStore(root / "reports.json"),
            JsonMapStore(root / "comments.json"),
            JsonMapStore(root / "receipts.json"),
        )
        self.package_store = JsonMapStore(root / "execution_packages.json")
        self.service = PullRequestIntelligenceService(
            azure_devops=self.azure,
            repository=repository,
            context_stores={"executionPackages": self.package_store},
            platform=self.platform,
        )

    def tearDown(self):
        self.temp.cleanup()

    def request(self, **overrides):
        value = {
            "projectId": "project-1",
            "repositoryId": "repo-1",
            "pullRequest": {
                "pullRequestId": "17",
                "title": "Add fault event details",
                "status": "active",
                "repositoryId": "repo-1",
                "sourceBranch": "refs/heads/feature/fault-details",
                "targetBranch": "refs/heads/main",
                "sourceCommitId": "commit-after",
                "linkedWorkItemIds": ["42"],
                "changedFiles": [
                    {"path": "src/fault_details.py", "changeType": "Modified"},
                    {"path": "tests/test_fault_details.py", "changeType": "Modified"},
                ],
                "repositorySnapshotBefore": "snapshot-1",
                "repositorySnapshotAfter": "snapshot-2",
            },
            "linkedWorkItems": [{"workItemId": "42", "title": "View fault details"}],
            "executionPackage": {
                "packageId": "package-42",
                "storyId": "42",
                "metadata": {"repositorySnapshotVersion": "snapshot-2"},
                "businessContext": {"taskObjective": "Show approved fault event details."},
                "acceptanceMapping": [
                    {"acceptanceCriteriaId": "AC-1", "acceptanceText": "Operator can view fault details."},
                    {"acceptanceCriteriaId": "AC-2", "acceptanceText": "Unauthorized users are denied."},
                ],
                "repositoryContext": {"relevantFiles": ["src/fault_details.py"]},
                "implementationBoundary": {"allowedModules": ["Fault Monitoring"], "blockedModules": ["Firmware"]},
            },
            "executionPlan": {"planId": "plan-42", "objective": "Implement fault detail retrieval and authorization."},
            "runtimeSession": {"sessionId": "session-42", "packageId": "package-42"},
            "engineeringDiff": {"diffId": "diff-42", "impact": {"level": "Medium"}},
            "validationResult": {
                "reportId": "validation-42",
                "status": "Passed",
                "acceptanceCoverageScore": 100,
                "testCoverageScore": 90,
                "acceptanceResults": [
                    {"acceptanceCriteriaId": "AC-1", "status": "Implemented", "evidence": ["src/fault_details.py"]},
                    {"acceptanceCriteriaId": "AC-2", "status": "Implemented", "evidence": ["tests/test_fault_details.py"]},
                ],
            },
            "qaResult": {"reportId": "qa-42", "status": "Ready", "missingTests": []},
            "memoryCandidates": [{"candidateId": "memory-42", "status": "PendingApproval"}],
            "prCandidate": {"candidateId": "candidate-42", "summary": {"title": "Fault details"}},
        }
        value.update(overrides)
        return value

    def test_pr_linked_to_execution_package(self):
        request = self.request()
        package = request.pop("executionPackage")
        self.package_store.write({package["packageId"]: package})
        report = self.service.analyze("17", request, correlation_id="corr-pr-17")
        self.assertEqual("ReadyForReview", report["status"])
        self.assertTrue(report["context"]["executionPackage"]["available"])
        self.assertEqual("package-42", report["context"]["executionPackage"]["id"])
        self.assertEqual("corr-pr-17", report["diagnostics"]["correlationId"])

    def test_pr_without_linked_story_needs_review(self):
        request = self.request(linkedWorkItems=[])
        request["pullRequest"]["linkedWorkItemIds"] = []
        report = self.service.analyze("17", request)
        self.assertEqual("NeedsReview", report["status"])
        self.assertIn("No linked Azure DevOps work item is available.", report["warnings"])

    def test_missing_acceptance_criterion_requires_changes(self):
        request = self.request()
        request["validationResult"]["acceptanceResults"][1]["status"] = "Missing"
        report = self.service.analyze("17", request)
        self.assertEqual("ChangesRequired", report["status"])
        self.assertEqual(["AC-2"], [item["acceptanceCriteriaId"] for item in report["missingCriteria"]])

    def test_unrelated_file_needs_review(self):
        request = self.request()
        request["pullRequest"]["changedFiles"].append({"path": "src/unrelated_billing.py"})
        report = self.service.analyze("17", request)
        self.assertEqual("NeedsReview", report["status"])
        self.assertIn("src/unrelated_billing.py", report["unrelatedChanges"])

    def test_blocked_module_change_requires_changes(self):
        request = self.request()
        request["pullRequest"]["changedFiles"].append({"path": "src/firmware/rollout.py"})
        report = self.service.analyze("17", request)
        self.assertEqual("ChangesRequired", report["status"])
        self.assertTrue(report["blockedModuleChanges"])

    def test_missing_tests_marks_qa_incomplete(self):
        request = self.request()
        request["pullRequest"]["changedFiles"] = [{"path": "src/fault_details.py"}]
        request["validationResult"]["testCoverageScore"] = 40
        report = self.service.analyze("17", request)
        self.assertEqual("QAIncomplete", report["status"])
        self.assertTrue(report["missingTests"])

    def test_documentation_only_pr_does_not_invent_code_or_test_gaps(self):
        request = self.request()
        request["pullRequest"]["changedFiles"] = [{"path": "docs/fault-details.md"}]
        request["executionPackage"]["repositoryContext"]["relevantFiles"] = ["docs/fault-details.md"]
        request["validationResult"]["testCoverageScore"] = 0
        report = self.service.analyze("17", request)
        self.assertTrue(report["documentationOnly"])
        self.assertEqual([], report["missingTests"])
        self.assertNotEqual("ChangesRequired", report["status"])

    def test_stale_snapshot_needs_review(self):
        request = self.request()
        request["executionPackage"]["metadata"]["repositorySnapshotVersion"] = "snapshot-1"
        report = self.service.analyze("17", request)
        self.assertEqual("NeedsReview", report["status"])
        self.assertTrue(report["diagnostics"]["staleSnapshot"])

    def test_approved_comment_is_posted_once(self):
        self.service.analyze("17", self.request())
        preview = self.service.preview_comment("17", {"projectId": "project-1"})
        payload = {
            "commentPreviewId": preview["commentPreviewId"], "approved": True,
            "approvedBy": "reviewer@example.com", "idempotencyKey": "post-17-v1",
            "connectionId": "ado-1", "projectId": "project-1", "repositoryId": "repo-1",
        }
        result = self.service.post_approved_comment("17", payload, correlation_id="corr-comment")
        replay = self.service.post_approved_comment("17", payload, correlation_id="corr-comment")
        self.assertTrue(result["posted"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(1, len(self.writer.calls))
        self.assertEqual(1, self.platform.audit.by_correlation("corr-comment")["count"])

    def test_comment_preview_approval_does_not_post_to_azure_devops(self):
        self.service.analyze("17", self.request())
        preview = self.service.preview_comment("17", {"projectId": "project-1"})
        approved = self.service.approve_comment_preview(preview["commentPreviewId"], "reviewer@example.com", "Reviewed in Approval Center")
        self.assertEqual("Approved", approved["approvalStatus"])
        self.assertFalse(approved["posted"])
        self.assertEqual([], self.writer.calls)

    def test_approved_comment_is_blocked_when_pr_revision_changes(self):
        request = self.request()
        self.service.analyze("17", request)
        preview = self.service.preview_comment("17", {"projectId": "project-1"})
        changed = dict(request["pullRequest"])
        changed["sourceCommitId"] = "commit-newer"
        self.cache.upsert("project-1", "pullRequests", "17", changed)
        payload = {
            "commentPreviewId": preview["commentPreviewId"], "approved": True,
            "approvedBy": "reviewer@example.com", "idempotencyKey": "post-17-stale",
            "connectionId": "ado-1", "projectId": "project-1", "repositoryId": "repo-1",
        }
        with self.assertRaisesRegex(ValueError, "changed after comment approval"):
            self.service.post_approved_comment("17", payload, correlation_id="corr-comment-stale")
        self.assertEqual([], self.writer.calls)

    def test_duplicate_webhook_is_idempotent(self):
        request = self.request()
        self.cache.upsert("project-1", "pullRequests", "17", request["pullRequest"])
        self.cache.upsert("project-1", "workItems", "42", request["linkedWorkItems"][0])
        event = {"eventId": "event-17", "eventType": "PullRequestUpdated", "projectId": "project-1", "payload": {"pullRequestId": "17"}}
        self.service.handle(event)
        first = self.platform.events.list_recent("PullRequestAnalysisCompleted")["count"]
        self.service.handle(event)
        self.assertEqual(first, self.platform.events.list_recent("PullRequestAnalysisCompleted")["count"])

    def test_analysis_never_posts_approves_or_merges(self):
        report = self.service.analyze("17", self.request())
        self.assertEqual(0, len(self.writer.calls))
        self.assertEqual(0, report["diagnostics"]["automaticCommentsPosted"])
        self.assertEqual(0, report["diagnostics"]["pullRequestsApproved"])
        self.assertEqual(0, report["diagnostics"]["pullRequestsMerged"])
        self.assertNotEqual("MergeReady", report["status"])

    def test_required_api_routes(self):
        wrapper = SimpleNamespace(pull_requests=self.service, estimation=None)
        app = FastAPI()
        app.include_router(build_ado_intelligence_router(wrapper))
        client = TestClient(app)
        response = client.post("/ado-intelligence/pull-requests/17/analyze", json=self.request())
        self.assertEqual(200, response.status_code)
        self.assertEqual(200, client.get("/ado-intelligence/pull-requests/17/report?projectId=project-1").status_code)
        preview = client.post("/ado-intelligence/pull-requests/17/comment-preview", json={"projectId": "project-1"})
        self.assertEqual("PendingApproval", preview.json()["approvalStatus"])
        denied = client.post("/ado-intelligence/pull-requests/17/post-approved-comment", json={"commentPreviewId": preview.json()["commentPreviewId"]})
        self.assertEqual(403, denied.status_code)
        self.assertEqual(200, client.post("/ado-intelligence/pull-requests/17/reanalyze", json=self.request()).status_code)

    def test_real_ado_pr_context_normalizes_commits_links_and_changed_files(self):
        service = AzureDevOpsPullRequestService(ReadConnections())
        context = service.get_pull_request_context("ado-1", "project-1", "repo-1", 17)
        self.assertEqual(["42"], context["linkedWorkItemIds"])
        self.assertEqual("commit-2", context["commits"][0]["commitId"])
        self.assertEqual("/src/fault_details.py", context["changedFiles"][0]["path"])


if __name__ == "__main__":
    unittest.main()
