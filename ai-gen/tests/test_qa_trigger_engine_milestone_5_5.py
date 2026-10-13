from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.execution_runtime import (
    QAExecutionPlanRepository,
    QATriggerEngine,
    QATriggerService,
    build_qa_trigger_router,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


CHANGE_FIELDS = {
    "API": "apiChanges",
    "Module": "moduleChanges",
    "Service": "serviceChanges",
    "Dependency": "dependencyChanges",
    "Architecture": "architectureChanges",
    "Test": "testChanges",
    "Security": "securityChanges",
    "Configuration": "configurationChanges",
    "Database": "databaseChanges",
    "Documentation": "documentationChanges",
    "Refactoring": "refactoringChanges",
    "BreakingChange": "breakingChanges",
}


def _empty_changes() -> dict:
    return {"added": [], "modified": [], "removed": [], "moved": []}


def _diff(change_type: str | None = None, *, name: str = "Device health change", diff_id: str = "engineering-diff-55") -> dict:
    value = {
        "diffId": diff_id,
        "sessionId": "execution-session-55",
        "correlationId": "corr-qa-trigger-55",
        "confidence": 0.91,
        "dependencyGraphChanges": {
            "nodesAdded": [],
            "nodesRemoved": [],
            "nodesModified": [],
            "edgesAdded": [],
            "edgesRemoved": [],
            "edgesModified": [],
        },
        "repositorySnapshotAfter": {"repositoryId": "repo-gridhub"},
    }
    for field in CHANGE_FIELDS.values():
        value[field] = _empty_changes()
    if change_type:
        value[CHANGE_FIELDS[change_type]]["modified"].append({"changeType": "Modified", "name": name})
    return value


def _validation(status: str = "Passed", **overrides) -> dict:
    value = {
        "reportId": "validation-report-55",
        "sessionId": "execution-session-55",
        "correlationId": "corr-qa-trigger-55",
        "status": status,
        "acceptanceCoverageScore": 92,
        "testCoverageScore": 84,
        "confidence": 0.9,
        "violations": [],
        "recommendations": [],
    }
    value.update(overrides)
    return value


def _manifest(**overrides) -> dict:
    value = {
        "manifestId": "execution-manifest-55",
        "relevantFiles": [],
        "implementationGuidance": [],
        "qaGuidance": [],
    }
    value.update(overrides)
    return value


class QATriggerEngineMilestone55Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.engine = QATriggerEngine()
        self.service = QATriggerService(
            QAExecutionPlanRepository(JsonMapStore(self.root / "qa-execution-plans.json")),
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def plan(self, diff: dict, validation: dict | None = None, manifest: dict | None = None) -> dict:
        return self.engine.plan(diff, validation or _validation(), manifest or _manifest())

    def test_api_change_requests_contract_and_access_coverage(self) -> None:
        plan = self.plan(_diff("API", name="GET /devices/{id}"))

        self.assertEqual(plan["decision"], "Requested")
        self.assertTrue(plan["needUnitTests"])
        self.assertTrue(plan["needIntegrationTests"])
        self.assertTrue(plan["needRegressionTests"])
        self.assertTrue(plan["needPermissionTests"])
        self.assertTrue(plan["needSmokeTests"])
        self.assertFalse(plan["needSecurityTests"])
        self.assertFalse(plan["needUITests"])

    def test_database_change_requests_integration_performance_and_smoke(self) -> None:
        plan = self.plan(_diff("Database", name="DeviceHealth migration"))

        self.assertTrue(plan["needIntegrationTests"])
        self.assertTrue(plan["needRegressionTests"])
        self.assertTrue(plan["needPerformanceTests"])
        self.assertTrue(plan["needSmokeTests"])

    def test_ui_change_is_detected_from_ranked_repository_file(self) -> None:
        plan = self.plan(
            _diff("Module", name="Device health presentation"),
            manifest=_manifest(relevantFiles=[{"path": "src/DeviceHealthPage.tsx", "confidence": 0.96}]),
        )

        self.assertTrue(plan["changeSummary"]["uiChangeDetected"])
        self.assertTrue(plan["needUITests"])
        self.assertTrue(plan["needUnitTests"])
        self.assertTrue(plan["needRegressionTests"])
        self.assertTrue(plan["needSmokeTests"])

    def test_documentation_overview_is_not_misclassified_as_ui(self) -> None:
        plan = self.plan(_diff("Documentation", name="docs/overview.md"))

        self.assertEqual(plan["decision"], "Skipped")
        self.assertFalse(plan["changeSummary"]["uiChangeDetected"])
        self.assertEqual(plan["eventType"], "QASkipped")

    def test_configuration_change_adds_security_for_sensitive_configuration(self) -> None:
        ordinary = self.plan(_diff("Configuration", name="config/device-health.json"))
        sensitive = self.plan(_diff("Configuration", name="config/authorization-policy.json"))

        self.assertTrue(ordinary["needSmokeTests"])
        self.assertTrue(ordinary["needRegressionTests"])
        self.assertFalse(ordinary["needSecurityTests"])
        self.assertTrue(sensitive["needSecurityTests"])
        self.assertTrue(sensitive["needPermissionTests"])

    def test_architecture_change_requests_cross_boundary_coverage(self) -> None:
        plan = self.plan(_diff("Architecture", name="Telemetry ingestion boundary"))

        self.assertTrue(plan["needIntegrationTests"])
        self.assertTrue(plan["needRegressionTests"])
        self.assertTrue(plan["needPerformanceTests"])
        self.assertTrue(plan["needSmokeTests"])

    def test_failed_validation_skips_qa(self) -> None:
        plan = self.plan(_diff("API"), validation=_validation("Failed"))

        self.assertEqual(plan["decision"], "Skipped")
        self.assertFalse(plan["qaRequired"])
        self.assertEqual(plan["requiredActivities"], [])
        self.assertEqual(plan["eventType"], "QASkipped")

    def test_validation_findings_add_targeted_security_and_performance_tests(self) -> None:
        validation = _validation(
            violations=[{"message": "Authorization permission coverage is missing."}],
            recommendations=["Verify response time under expected load."],
        )
        plan = self.plan(_diff("Service"), validation=validation)

        self.assertTrue(plan["needSecurityTests"])
        self.assertTrue(plan["needPermissionTests"])
        self.assertTrue(plan["needPerformanceTests"])

    def test_service_persists_plan_and_publishes_requested_and_skipped_events(self) -> None:
        requested = self.service.evaluate({
            "engineeringDiff": _diff("API"),
            "validationResult": _validation(),
            "executionManifest": _manifest(),
        })
        skipped = self.service.evaluate({
            "engineeringDiff": _diff("Documentation", name="docs/release-notes.md", diff_id="engineering-diff-docs-55"),
            "validationResult": {**_validation(), "reportId": "validation-report-docs-55"},
            "executionManifest": _manifest(),
        })

        self.assertEqual(self.service.get(requested["planId"]), requested)
        self.assertEqual(skipped["decision"], "Skipped")
        self.assertEqual(self.platform.events.list_recent(event_type="QARequested")["count"], 1)
        self.assertEqual(self.platform.events.list_recent(event_type="QASkipped")["count"], 1)
        event = self.platform.events.list_recent(event_type="QARequested")["events"][0]
        self.assertEqual(event["correlationId"], "corr-qa-trigger-55")
        self.assertFalse(event["payload"]["invoked"])
        self.assertFalse(requested["diagnostics"]["testsGenerated"])

    def test_api_contract_exposes_evaluate_and_retrieve(self) -> None:
        router = build_qa_trigger_router(self.service)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}

        self.assertEqual(set(routes), {
            ("POST", "/qa-trigger/evaluate"),
            ("GET", "/qa-trigger/{plan_id}"),
        })
        plan = routes[("POST", "/qa-trigger/evaluate")]({
            "engineeringDiff": _diff("Architecture"),
            "validationResult": _validation(),
            "executionManifest": _manifest(),
        })
        self.assertEqual(routes[("GET", "/qa-trigger/{plan_id}")](plan["planId"]), plan)


if __name__ == "__main__":
    unittest.main()
