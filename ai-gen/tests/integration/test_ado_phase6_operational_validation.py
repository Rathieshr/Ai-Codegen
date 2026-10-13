from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_hardening import AzureDevOpsArchitectureVerifier, AzureDevOpsOperationalValidator, LiveTestSafetyPolicy, build_ado_operational_router
from backend.ado_hardening.architecture import REQUIRED_STAGES
from backend.platform import PlatformFoundation
from backend.platform_sdk import HEIPhase6Sdk


class MockOperationalExecutor:
    is_mock = True

    def __init__(self, *, failures=(), omit_stage="", evidence_overrides=None):
        self.failures = set(failures)
        self.omit_stage = omit_stage
        self.evidence_overrides = evidence_overrides or {}
        self.sdk = HEIPhase6Sdk(intelligence=None, automation=None, agent=None, azure_devops=object(), platform=None)

    def execute(self, flow_id, request, correlation_id):
        evidence = {
            "preview": True, "approved": True, "idempotent": True,
            "revisionProtected": True, "audited": True, "stableApi": True,
            "readWriteSeparated": True, "apiVisible": True,
            "executionPackage": True, "actualDiff": True,
            "adoWorkItems": True, "burndown": True, "forecast": True,
        }
        evidence.update(self.evidence_overrides.get(flow_id, {}))
        stages = [stage for stage in REQUIRED_STAGES if stage != self.omit_stage]
        return {"passed": flow_id not in self.failures, "details": f"{flow_id} contract validated.", "evidence": evidence, "stages": stages}


class AzureDevOpsOperationalValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.safety = LiveTestSafetyPolicy(False, False, frozenset(), frozenset({"production"}))
        self.backend_root = Path(__file__).parents[2] / "backend"

    def tearDown(self):
        self.temp.cleanup()

    def validator(self, executor=None):
        return AzureDevOpsOperationalValidator(self.root / "operational", executor=executor or MockOperationalExecutor(), architecture=AzureDevOpsArchitectureVerifier(self.backend_root), safety=self.safety, platform=self.platform)

    def test_all_nine_flows_share_one_correlation_trace(self):
        report = self.validator().run({"mode": "Mocked", "projectId": "ado-test", "allowWrites": True})
        self.assertEqual(9, len(report["flows"]))
        self.assertEqual({report["correlationId"]}, {item["correlationId"] for item in report["flows"]})
        self.assertEqual(set(REQUIRED_STAGES), {item["stage"] for item in report["trace"]})
        self.assertEqual(report["runId"], self.validator().trace(report["correlationId"])["runId"])

    def test_mock_contract_passes_but_never_unlocks_ui(self):
        report = self.validator().run({"mode": "Mocked", "projectId": "ado-test", "allowWrites": True})
        self.assertTrue(all(item["passed"] for item in report["qualityGates"]))
        self.assertEqual("Blocked", report["readiness"]["status"])
        self.assertFalse(report["readiness"]["liveEvidence"])

    def test_intelligence_modules_use_platform_sdk_boundary(self):
        report = self.validator().run({"mode": "Mocked", "projectId": "ado-test"})
        self.assertTrue(report["architecture"]["passed"], report["architecture"])
        self.assertEqual([], report["architecture"]["violations"])

    def test_missing_architecture_stage_blocks_gate(self):
        report = self.validator(MockOperationalExecutor(omit_stage="PlatformJobEvent")).run({"mode": "Mocked", "projectId": "ado-test"})
        self.assertFalse(next(item for item in report["qualityGates"] if item["gateId"] == "architecture_boundary")["passed"])

    def test_incomplete_write_controls_block_gate(self):
        executor = MockOperationalExecutor(evidence_overrides={"approved-work-item-update": {"revisionProtected": False}})
        report = self.validator(executor).run({"mode": "Mocked", "projectId": "ado-test"})
        self.assertFalse(next(item for item in report["qualityGates"] if item["gateId"] == "write_controls")["passed"])

    def test_pr_and_sprint_grounding_are_hard_gates(self):
        executor = MockOperationalExecutor(evidence_overrides={"approved-pr-comment": {"actualDiff": False}, "real-sprint-report": {"adoWorkItems": False}})
        report = self.validator(executor).run({"mode": "Mocked", "projectId": "ado-test"})
        failed = {item["gateId"] for item in report["qualityGates"] if not item["passed"]}
        self.assertTrue({"pr_grounding", "real_sprint_data"}.issubset(failed))

    def test_failure_and_reconciliation_are_api_visible(self):
        executor = MockOperationalExecutor(evidence_overrides={"scheduled-reconciliation": {"apiVisible": False}})
        report = self.validator(executor).run({"mode": "Mocked", "projectId": "ado-test"})
        self.assertFalse(next(item for item in report["qualityGates"] if item["gateId"] == "failure_retry_visibility")["passed"])

    def test_api_exposes_run_report_readiness_and_trace_only(self):
        validator = self.validator(); app = FastAPI(); app.include_router(build_ado_operational_router(validator)); client = TestClient(app)
        report = client.post("/ado-operational-validation/run", json={"mode": "Mocked", "projectId": "ado-test"}).json()
        self.assertEqual(report["runId"], client.get("/ado-operational-validation/report").json()["runId"])
        self.assertEqual(report["runId"], client.get(f"/ado-operational-validation/traces/{report['correlationId']}").json()["runId"])
        self.assertEqual("Blocked", client.get("/ado-operational-validation/readiness").json()["status"])


if __name__ == "__main__":
    unittest.main()
