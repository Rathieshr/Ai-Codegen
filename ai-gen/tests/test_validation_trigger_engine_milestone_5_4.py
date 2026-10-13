from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.execution_runtime import (
    ValidationTriggerEngine,
    ValidationTriggerRepository,
    ValidationTriggerService,
    build_validation_trigger_router,
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


def _diff(change_type: str | None = None, *, impact: str = "Low", name: str = "Device health change") -> dict:
    value = {
        "diffId": "engineering-diff-54",
        "sessionId": "execution-session-54",
        "impact": {"level": impact, "score": 5, "reasons": []},
        "dependencyGraphChanges": {
            "nodesAdded": [], "nodesRemoved": [], "nodesModified": [],
            "edgesAdded": [], "edgesRemoved": [], "edgesModified": [],
        },
        "repositorySnapshotAfter": {"repositoryId": "repo-gridhub"},
    }
    for field in CHANGE_FIELDS.values():
        value[field] = _empty_changes()
    if change_type:
        field = CHANGE_FIELDS[change_type]
        value[field]["modified"].append({"changeType": "Modified", "name": name})
    return value


def _result(*artifacts: dict, status: str = "Completed") -> dict:
    return {
        "resultId": "execution-result-54",
        "sessionId": "execution-session-54",
        "correlationId": "corr-validation-trigger-54",
        "status": status,
        "engineeringArtifacts": list(artifacts),
    }


def _manifest(**overrides) -> dict:
    value = {
        "manifestId": "execution-manifest-54",
        "validationGuidance": {},
        "engineeringStandards": [],
        "risks": [],
    }
    value.update(overrides)
    return value


class ValidationTriggerEngineMilestone54Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = ValidationTriggerService(
            ValidationTriggerRepository(JsonMapStore(self.root / "validation-triggers.json")),
            platform=self.platform,
        )
        self.engine = ValidationTriggerEngine()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def decide(self, diff: dict, result: dict | None = None, manifest: dict | None = None, **options) -> dict:
        return self.engine.decide(diff, result or _result(), manifest or _manifest(), **options)

    def test_every_hard_engineering_change_type_requires_validation(self) -> None:
        required_types = ["API", "Module", "Service", "Dependency", "Architecture", "Test", "Security", "Database", "Refactoring", "BreakingChange"]
        for change_type in required_types:
            with self.subTest(change_type=change_type):
                decision = self.decide(_diff(change_type))
                self.assertEqual(decision["decision"], "Required")
                self.assertTrue(decision["validationRequired"])
                self.assertEqual(decision["eventType"], "ValidationRequested")
                self.assertIn(change_type, decision["reason"])

    def test_dependency_graph_change_requires_validation(self) -> None:
        diff = _diff()
        diff["dependencyGraphChanges"]["edgesAdded"].append({"from": "Controller", "to": "Service", "type": "uses"})

        decision = self.decide(diff)

        self.assertEqual(decision["decision"], "Required")
        self.assertIn("DependencyGraph", decision["reason"])

    def test_documentation_only_and_comments_only_are_skipped(self) -> None:
        documentation = self.decide(_diff("Documentation", name="docs/device-health.md"))
        comments = self.decide(_diff(), _result({"type": "Comment", "title": "Clarify health status"}))

        self.assertEqual(documentation["decision"], "Skipped")
        self.assertEqual(documentation["reason"], "Only documentation changed.")
        self.assertEqual(comments["decision"], "Skipped")
        self.assertEqual(comments["reason"], "Only comments changed.")

    def test_configuration_change_is_conditional(self) -> None:
        ordinary = self.decide(_diff("Configuration", name="config/ui-layout.json"))
        sensitive = self.decide(_diff("Configuration", name="config/production-auth.json"))
        manifest_required = self.decide(
            _diff("Configuration", name="config/device-health.json"),
            manifest=_manifest(validationGuidance={"validationRequired": True}),
        )

        self.assertEqual(ordinary["decision"], "Skipped")
        self.assertEqual(sensitive["decision"], "Required")
        self.assertEqual(manifest_required["decision"], "Required")
        self.assertEqual(sensitive["rulesUsed"][0]["ruleId"], "configuration_conditional")

    def test_high_impact_precedes_documentation_skip(self) -> None:
        decision = self.decide(_diff("Documentation", impact="High"))

        self.assertEqual(decision["decision"], "Required")
        self.assertEqual(decision["rulesUsed"][0]["ruleId"], "high_impact_requires_validation")

    def test_manual_override_precedes_normal_engineering_rules(self) -> None:
        skipped = self.decide(
            _diff("API"),
            manual_override={"decision": "skip", "reason": "Validated externally.", "actor": "release-admin"},
        )
        required = self.decide(_diff("Documentation"), manual_override="require")

        self.assertEqual(skipped["decision"], "Skipped")
        self.assertEqual(skipped["reason"], "Validated externally.")
        self.assertEqual(skipped["manualOverride"]["actor"], "release-admin")
        self.assertEqual(required["decision"], "Required")
        self.assertEqual(required["rulesUsed"][0]["ruleId"], "manual_override")

    def test_policy_precedence_blocks_or_requires_before_manual_override(self) -> None:
        blocked = self.decide(
            _diff("Documentation"),
            manual_override="require",
            policy={"blocked": True, "reason": "Manifest approval expired."},
        )
        required = self.decide(
            _diff("Documentation"),
            manual_override="skip",
            policy={"validationRequired": True},
        )
        skip_prohibited = self.decide(
            _diff("API"),
            manual_override="skip",
            policy={"allowManualSkip": False},
        )

        self.assertEqual(blocked["decision"], "Blocked")
        self.assertIn("approval expired", blocked["reason"])
        self.assertEqual(required["decision"], "Required")
        self.assertEqual(skip_prohibited["decision"], "Blocked")

    def test_failed_execution_result_blocks_validation(self) -> None:
        decision = self.decide(_diff("API"), _result(status="Failed"))

        self.assertEqual(decision["decision"], "Blocked")
        self.assertEqual(decision["eventType"], "ValidationBlocked")
        self.assertFalse(decision["validationRequired"])

    def test_service_persists_decisions_and_emits_all_event_types(self) -> None:
        required = self.service.evaluate({
            "engineeringDiff": _diff("API"), "executionResult": _result(), "executionManifest": _manifest(),
        })
        skipped = self.service.evaluate({
            "engineeringDiff": {**_diff("Documentation"), "diffId": "engineering-diff-docs"},
            "executionResult": {**_result(), "resultId": "execution-result-docs"},
            "executionManifest": _manifest(),
        })
        blocked = self.service.evaluate({
            "engineeringDiff": {**_diff("API"), "diffId": "engineering-diff-blocked"},
            "executionResult": {**_result(), "resultId": "execution-result-blocked"},
            "executionManifest": _manifest(),
            "policy": {"blocked": True, "reason": "Release freeze."},
        })

        self.assertEqual(self.service.get(required["decisionId"]), required)
        self.assertEqual(skipped["decision"], "Skipped")
        self.assertEqual(blocked["decision"], "Blocked")
        self.assertEqual(self.platform.events.list_recent(event_type="ValidationRequested")["count"], 1)
        self.assertEqual(self.platform.events.list_recent(event_type="ValidationSkipped")["count"], 1)
        self.assertEqual(self.platform.events.list_recent(event_type="ValidationBlocked")["count"], 1)
        event = self.platform.events.list_recent(event_type="ValidationRequested")["events"][0]
        self.assertEqual(event["correlationId"], "corr-validation-trigger-54")
        self.assertFalse(event["payload"]["invoked"])

    def test_governance_policy_result_is_enforced(self) -> None:
        class BlockingGovernance:
            def enforce_policies(self, artifact, context):
                return {
                    "status": "Blocked",
                    "violations": [{"severity": "High", "message": "Approved manifest is required."}],
                }

        service = ValidationTriggerService(
            ValidationTriggerRepository(JsonMapStore(self.root / "governed-triggers.json")),
            governance=BlockingGovernance(),
            platform=self.platform,
        )
        decision = service.evaluate({
            "engineeringDiff": _diff("API"), "executionResult": _result(), "executionManifest": _manifest(),
            "manualOverride": "require",
        })

        self.assertEqual(decision["decision"], "Blocked")
        self.assertIn("Approved manifest", decision["reason"])
        self.assertEqual(decision["policy"]["governanceStatus"], "Blocked")

    def test_api_contract_and_invalid_request_failure_event(self) -> None:
        router = build_validation_trigger_router(self.service)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {
            ("POST", "/validation-trigger/evaluate"),
            ("GET", "/validation-trigger/{decision_id}"),
        })
        decision = routes[("POST", "/validation-trigger/evaluate")]({
            "engineeringDiff": _diff("API"), "executionResult": _result(), "executionManifest": _manifest(),
        })
        self.assertEqual(routes[("GET", "/validation-trigger/{decision_id}")](decision["decisionId"]), decision)
        with self.assertRaises(HTTPException):
            routes[("POST", "/validation-trigger/evaluate")]({})
        with self.assertRaises(HTTPException):
            routes[("GET", "/validation-trigger/{decision_id}")]("missing")


if __name__ == "__main__":
    unittest.main()
