"""Tests for Phase 3: ADO client, automation engine, and app endpoints."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch, call

from backend.ado.client import AdoClient, AdoConfig, AdoClientError
from backend.ado.automation import AdoAutomation, AutomationResult, ActionRecord


# ── AdoConfig tests ──────────────────────────────────────────────────────────

class AdoConfigTests(unittest.TestCase):
    def test_not_configured_when_env_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            # Ensure key vars not set
            import os
            for key in ("ADO_ORG_URL", "ADO_PROJECT", "ADO_PAT"):
                os.environ.pop(key, None)
            cfg = AdoConfig()
            self.assertFalse(cfg.is_configured)

    def test_configured_when_all_env_set(self) -> None:
        with patch.dict("os.environ", {
            "ADO_ORG_URL": "https://dev.azure.com/myorg",
            "ADO_PROJECT": "MyProject",
            "ADO_PAT": "secret-token",
        }, clear=False):
            cfg = AdoConfig()
            self.assertTrue(cfg.is_configured)

    def test_base64_pat_produces_basic_header(self) -> None:
        cfg = AdoConfig(org_url="https://dev.azure.com/org", project="Proj", pat="mytoken")
        header = cfg._base64_pat()
        self.assertTrue(header.startswith("Basic "))
        import base64
        decoded = base64.b64decode(header[6:]).decode()
        self.assertEqual(decoded, ":mytoken")

    def test_project_url_encodes_spaces(self) -> None:
        cfg = AdoConfig(org_url="https://dev.azure.com/org", project="My Project", pat="tok")
        self.assertIn("My%20Project", cfg.project_url)

    def test_base_url_strips_trailing_slash(self) -> None:
        cfg = AdoConfig(org_url="https://dev.azure.com/org/", project="P", pat="t")
        self.assertFalse(cfg.base_url.endswith("/"))


# ── AdoClient tests ───────────────────────────────────────────────────────────

class AdoClientTests(unittest.TestCase):
    def _make_client(self) -> AdoClient:
        cfg = AdoConfig(
            org_url="https://dev.azure.com/testorg",
            project="TestProject",
            pat="testpat",
        )
        return AdoClient(cfg)

    def test_not_configured_client_returns_false(self) -> None:
        client = AdoClient(AdoConfig())
        self.assertFalse(client.is_configured)

    def test_configured_client_returns_true(self) -> None:
        client = self._make_client()
        self.assertTrue(client.is_configured)

    def test_patch_work_item_builds_json_patch(self) -> None:
        client = self._make_client()
        sent_bodies: list[bytes] = []

        def fake_send(req):
            if req.data:
                sent_bodies.append(req.data)
            return {"id": 42, "rev": 2}

        with patch.object(client, "_send", side_effect=fake_send):
            client.patch_work_item(42, {"System.State": "Active"})

        self.assertEqual(len(sent_bodies), 1)
        ops = json.loads(sent_bodies[0])
        self.assertIsInstance(ops, list)
        self.assertEqual(ops[0]["op"], "replace")
        self.assertEqual(ops[0]["path"], "/fields/System.State")
        self.assertEqual(ops[0]["value"], "Active")

    def test_create_pr_prepends_refs_heads(self) -> None:
        client = self._make_client()
        sent_bodies: list[dict] = []

        def fake_send(req):
            if req.data:
                sent_bodies.append(json.loads(req.data))
            return {"pullRequestId": 7}

        with patch.object(client, "_send", side_effect=fake_send):
            client.create_pull_request(
                repo_id="repo-123",
                source_branch="feature/my-branch",
                target_branch="main",
                title="Test PR",
                draft=True,
            )

        body = sent_bodies[0]
        self.assertEqual(body["sourceRefName"], "refs/heads/feature/my-branch")
        self.assertEqual(body["targetRefName"], "refs/heads/main")
        self.assertTrue(body.get("isDraft"))

    def test_create_pr_does_not_double_prefix_refs(self) -> None:
        client = self._make_client()
        sent_bodies: list[dict] = []

        def fake_send(req):
            if req.data:
                sent_bodies.append(json.loads(req.data))
            return {"pullRequestId": 8}

        with patch.object(client, "_send", side_effect=fake_send):
            client.create_pull_request(
                repo_id="repo-456",
                source_branch="refs/heads/already-prefixed",
                target_branch="refs/heads/main",
                title="Already prefixed",
            )

        body = sent_bodies[0]
        self.assertEqual(body["sourceRefName"], "refs/heads/already-prefixed")
        self.assertNotIn("refs/heads/refs/heads", body["sourceRefName"])

    def test_send_raises_ado_client_error_on_http_error(self) -> None:
        import urllib.error
        client = self._make_client()

        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="https://example.com", code=401, msg="Unauthorized", hdrs=None, fp=None
        )):
            with self.assertRaises(AdoClientError) as ctx:
                client.get_work_item(99)
            self.assertEqual(ctx.exception.status, 401)


# ── AdoAutomation tests ───────────────────────────────────────────────────────

class AdoAutomationTests(unittest.TestCase):
    def _make_automation(self) -> AdoAutomation:
        cfg = AdoConfig(
            org_url="https://dev.azure.com/testorg",
            project="TestProject",
            pat="testpat",
        )
        client = AdoClient(cfg)
        return AdoAutomation(client)

    def _sample_pipeline_state(self, stage: str = "ba") -> dict:
        return {
            "pipeline_id": "pipe-test-001",
            "work_item_id": "42",
            "current_stage": stage,
            "work_item": {"id": 42, "title": "Add login screen", "type": "User Story"},
            "stages": {
                stage: {
                    "status": "generated",
                    "approved": True,
                    "output": {
                        "summary": "User can log in with phone OTP",
                        "base_flows": ["login", "otp_verification"],
                        "acceptance_criteria": "6-digit OTP, 3-minute expiry",
                    },
                }
            },
            "repo_context": {
                "resolved_repo_id": "repo-abc",
                "resolved_branch_name": "feature/login-otp",
            },
        }

    def test_skipped_when_not_configured(self) -> None:
        automation = AdoAutomation(AdoClient(AdoConfig()))
        result = automation.run_for_stage("pipe-1", "ba", self._sample_pipeline_state("ba"))
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(result.actions[0].status, "skipped")

    def test_state_update_called_for_ba_stage(self) -> None:
        automation = self._make_automation()
        with patch.object(automation._client, "patch_work_item", return_value={"id": 42, "rev": 2}) as mock_patch, \
             patch.object(automation._client, "add_work_item_comment", return_value={"id": 99}):
            result = automation.run_for_stage("pipe-1", "ba", self._sample_pipeline_state("ba"))

        mock_patch.assert_called_once_with(42, {"System.State": "Active"})
        state_action = next((a for a in result.actions if a.action == "update_work_item_state"), None)
        self.assertIsNotNone(state_action)
        self.assertEqual(state_action.status, "success")

    def test_comment_posted_for_ba_stage(self) -> None:
        automation = self._make_automation()
        with patch.object(automation._client, "patch_work_item", return_value={"id": 42, "rev": 2}), \
             patch.object(automation._client, "add_work_item_comment", return_value={"id": 55}) as mock_comment:
            automation.run_for_stage("pipe-1", "ba", self._sample_pipeline_state("ba"))

        mock_comment.assert_called_once()
        comment_text = mock_comment.call_args[0][1]
        self.assertIn("[ai-gen Approval]", comment_text)
        self.assertIn("ba", comment_text)

    def test_pr_created_for_dev_packet(self) -> None:
        automation = self._make_automation()
        state = self._sample_pipeline_state("dev_packet")
        with patch.object(automation._client, "patch_work_item", return_value={"id": 42, "rev": 3}), \
             patch.object(automation._client, "add_work_item_comment", return_value={"id": 56}), \
             patch.object(automation._client, "create_pull_request", return_value={"pullRequestId": 11}) as mock_pr:
            result = automation.run_for_stage("pipe-1", "dev_packet", state)

        mock_pr.assert_called_once()
        pr_action = next((a for a in result.actions if a.action == "create_pull_request"), None)
        self.assertIsNotNone(pr_action)
        self.assertEqual(pr_action.status, "success")

    def test_pr_skipped_when_no_branch(self) -> None:
        automation = self._make_automation()
        state = self._sample_pipeline_state("dev_packet")
        state["repo_context"] = {}   # no branch
        with patch.object(automation._client, "patch_work_item", return_value={"id": 42, "rev": 3}), \
             patch.object(automation._client, "add_work_item_comment", return_value={"id": 57}):
            result = automation.run_for_stage("pipe-1", "dev_packet", state)

        pr_action = next((a for a in result.actions if a.action == "create_pull_request"), None)
        self.assertIsNotNone(pr_action)
        self.assertEqual(pr_action.status, "skipped")

    def test_critic_stage_transitions_to_resolved(self) -> None:
        automation = self._make_automation()
        state = self._sample_pipeline_state("critic")
        with patch.object(automation._client, "patch_work_item", return_value={"id": 42, "rev": 4}) as mock_patch, \
             patch.object(automation._client, "add_work_item_comment", return_value={"id": 58}):
            automation.run_for_stage("pipe-1", "critic", state)

        mock_patch.assert_called_once_with(42, {"System.State": "Resolved"})

    def test_ado_error_is_captured_not_raised(self) -> None:
        automation = self._make_automation()
        state = self._sample_pipeline_state("ba")
        # Make patch_work_item raise — automation should catch it and record failure
        with patch.object(automation._client, "patch_work_item",
                          side_effect=AdoClientError("Forbidden", status=403)), \
             patch.object(automation._client, "add_work_item_comment",
                          side_effect=AdoClientError("Forbidden", status=403)):
            result = automation.run_for_stage("pipe-1", "ba", state)

        failed = [a for a in result.actions if a.status == "failed"]
        self.assertTrue(len(failed) >= 1)
        self.assertTrue(result.has_failures)

    def test_result_to_dict_structure(self) -> None:
        result = AutomationResult(pipeline_id="p1", stage="ba", work_item_id=42)
        result.actions.append(ActionRecord(action="test", status="success", detail="ok"))
        d = result.to_dict()
        self.assertIn("pipeline_id", d)
        self.assertIn("actions", d)
        self.assertIn("has_failures", d)
        self.assertIn("summary", d)


if __name__ == "__main__":
    unittest.main()
