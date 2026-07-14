from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ado_hardening import AzureDevOpsHardeningHarness, LiveTestSafetyError, LiveTestSafetyPolicy, build_ado_hardening_router
from backend.platform import PlatformFoundation


OPERATIONS = {
    "manual-requirement-hierarchy": ["hierarchy_creation_preview", "hierarchy_application"],
    "existing-epic-analysis": ["work_item_analysis"],
    "existing-story-estimation": ["work_item_analysis", "estimation"],
    "pull-request-approved-comment": ["pr_analysis"],
    "stale-work-item-recommendation": ["work_item_analysis"],
    "sprint-burndown-risk": ["sprint_report"],
    "build-failure-agent-response": ["agent_response"],
    "duplicate-webhook-idempotency": ["incremental_sync"],
    "permission-loss-safe-failure": ["hierarchy_creation_preview"],
    "azure-devops-outage-recovery": ["initial_sync"],
}


class MockPhase6Executor:
    is_mock = True

    def __init__(self, failures=None):
        self.failures = set(failures or [])
        self.calls = []

    def execute(self, scenario_id, request, correlation_id):
        self.calls.append((scenario_id, request.get("projectId"), correlation_id))
        return {
            "passed": scenario_id not in self.failures,
            "details": f"{scenario_id} {'failed' if scenario_id in self.failures else 'passed'} in isolated mocked ADO.",
            "operations": OPERATIONS[scenario_id],
            "evidence": {
                "previewed": True,
                "approved": bool(request.get("allowWrites")),
                "revisionProtected": True,
                "idempotent": True,
                "audited": True,
            },
        }

    def security_probe(self, request):
        checks = [
            {"checkId": "credentials_protected", "passed": True, "details": "Only secret references are stored."},
            {"checkId": "minimum_scopes", "passed": True, "details": "Read and write scopes are separated."},
            {"checkId": "no_arbitrary_patch_api", "passed": True, "details": "Only approved commands are exposed."},
            {"checkId": "audit_complete", "passed": True, "details": "Before and after state is correlated."},
            {"checkId": "project_isolation", "passed": True, "details": "Cache and mappings are project scoped."},
        ]
        return {"passed": True, "checks": checks}


class AzureDevOpsPhase6HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.safety = LiveTestSafetyPolicy(False, False, frozenset(), frozenset({"production"}))

    def tearDown(self):
        self.temp.cleanup()

    def harness(self, executor=None, safety=None):
        return AzureDevOpsHardeningHarness(self.root / "hardening", executor=executor or MockPhase6Executor(), safety=safety or self.safety, platform=self.platform)

    def test_all_ten_mocked_end_to_end_scenarios_pass(self):
        executor = MockPhase6Executor()
        report = self.harness(executor).run({"mode": "Mocked", "projectId": "ado-test", "allowWrites": True})
        self.assertEqual(10, len(report["scenarios"]))
        self.assertTrue(all(item["passed"] for item in report["scenarios"]))
        self.assertEqual("Command Center Ready", report["readiness"]["status"])
        self.assertEqual(10, len(executor.calls))

    def test_security_reliability_and_performance_gates_are_reported(self):
        report = self.harness().run({"mode": "Mocked", "projectId": "ado-test"})
        self.assertTrue(report["security"]["passed"])
        self.assertTrue(report["reliability"]["passed"])
        self.assertTrue(report["performance"]["passed"])
        self.assertEqual(9, report["performance"]["measuredOperations"])
        self.assertEqual({"end_to_end_scenarios", "security", "reliability", "performance", "write_safety"}, {item["gateId"] for item in report["qualityGates"]})

    def test_failed_scenario_blocks_command_center_readiness(self):
        report = self.harness(MockPhase6Executor({"permission-loss-safe-failure"})).run({"mode": "Mocked", "projectId": "ado-test"})
        self.assertEqual("Blocked", report["readiness"]["status"])
        self.assertFalse(report["reliability"]["passed"])
        self.assertTrue(report["readiness"]["blockers"])

    def test_report_is_persisted_and_readiness_uses_latest_run(self):
        harness = self.harness()
        report = harness.run({"mode": "Mocked", "projectId": "ado-test"})
        self.assertEqual(report["runId"], harness.get(report["runId"])["runId"])
        self.assertEqual(report["runId"], harness.latest()["runId"])
        self.assertEqual("Command Center Ready", harness.readiness()["status"])

    def test_each_scenario_writes_activity_and_audit_with_correlation(self):
        report = self.harness().run({"mode": "Mocked", "projectId": "ado-test"})
        activity = self.platform.activity.list_recent(limit=50)
        self.assertEqual(10, activity["count"])
        for scenario in report["scenarios"]:
            audit = self.platform.audit.by_correlation(scenario["correlationId"])["events"]
            self.assertEqual(1, len(audit))
            self.assertEqual("AzureDevOpsHardeningScenarioCompleted", audit[0]["action"])

    def test_live_mode_is_disabled_by_default(self):
        with self.assertRaises(LiveTestSafetyError):
            self.harness().run({"mode": "Live", "projectId": "ado-test", "projectConfirmation": "ado-test"})

    def test_production_project_is_always_rejected(self):
        safety = LiveTestSafetyPolicy(True, True, frozenset({"production"}), frozenset({"production"}))
        with self.assertRaises(LiveTestSafetyError):
            self.harness(safety=safety).run({"mode": "Live", "projectId": "production", "projectConfirmation": "production", "allowWrites": True})

    def test_live_write_requires_process_and_request_opt_in(self):
        safety = LiveTestSafetyPolicy(True, False, frozenset({"ado-test"}), frozenset())
        with self.assertRaises(LiveTestSafetyError):
            self.harness(safety=safety).run({"mode": "Live", "projectId": "ado-test", "projectConfirmation": "ado-test", "allowWrites": True})

    def test_hardening_api_exposes_reports_and_safety_error(self):
        harness = self.harness()
        app = FastAPI()
        app.include_router(build_ado_hardening_router(harness))
        client = TestClient(app)
        response = client.post("/ado-hardening/run", json={"mode": "Mocked", "projectId": "ado-test"})
        self.assertEqual(200, response.status_code)
        run_id = response.json()["runId"]
        self.assertEqual(run_id, client.get("/ado-hardening/report").json()["runId"])
        self.assertEqual(run_id, client.get(f"/ado-hardening/runs/{run_id}").json()["runId"])
        self.assertEqual("Command Center Ready", client.get("/ado-hardening/readiness").json()["status"])

    def test_api_contract_has_no_unrestricted_write_route(self):
        paths = {route.path for route in build_ado_hardening_router(self.harness()).routes}
        self.assertEqual({
            "/ado-hardening/run", "/ado-hardening/report", "/ado-hardening/runs",
            "/ado-hardening/runs/{run_id}", "/ado-hardening/readiness",
        }, paths)
        self.assertTrue(all("patch" not in path.lower() and "merge" not in path.lower() for path in paths))


if __name__ == "__main__":
    unittest.main()
