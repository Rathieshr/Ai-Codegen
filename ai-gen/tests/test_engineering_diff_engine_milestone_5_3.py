from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.execution_runtime import (
    EngineeringDiffRepository,
    EngineeringDiffService,
    build_engineering_diff_router,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


def _snapshot(
    snapshot_id: str,
    *,
    modules: list | None = None,
    apis: list | None = None,
    services: list | None = None,
    architecture: list | None = None,
    dependencies: list | None = None,
    files: list | None = None,
    symbols: list | None = None,
    graph: dict | None = None,
    diff: dict | None = None,
) -> dict:
    return {
        "snapshotId": snapshot_id,
        "repositoryId": "repo-gridhub",
        "version": snapshot_id.rsplit("-", 1)[-1],
        "branch": "main",
        "commitId": f"commit-{snapshot_id}",
        "modules": modules or [],
        "apis": apis or [],
        "services": services or [],
        "architecture": architecture or [],
        "dependencies": dependencies or [],
        "engineeringGraph": graph or {"nodes": [], "relationships": []},
        "metadata": {"files": files or [], "symbols": symbols or [], "diff": diff or {}},
    }


def _result(*artifacts: dict, structured: dict | None = None) -> dict:
    return {
        "interpretationId": "interpretation-53",
        "resultId": "execution-result-53",
        "sessionId": "execution-session-53",
        "correlationId": "corr-engineering-diff-53",
        "engineeringArtifacts": list(artifacts),
        "structuredExecutionResult": structured or {},
    }


class EngineeringDiffEngineMilestone53Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = EngineeringDiffService(
            EngineeringDiffRepository(JsonMapStore(self.root / "engineering-diffs.json")),
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, before: dict, after: dict, result: dict | None = None) -> dict:
        return self.service.build({
            "repositorySnapshotBefore": before,
            "repositorySnapshotAfter": after,
            "executionResult": result or _result(),
        })

    def test_api_addition_is_detected_semantically(self) -> None:
        before = _snapshot("snapshot-1", apis=[])
        after = _snapshot("snapshot-2", apis=[{"method": "GET", "route": "/api/device-health", "signature": "GET:DeviceHealth[]"}])

        diff = self.build(before, after)

        self.assertEqual(diff["newAPIs"][0]["name"], "GET /api/device-health")
        self.assertEqual(diff["newAPIs"][0]["changeType"], "Added")
        self.assertEqual(diff["impact"]["level"], "Medium")
        self.assertFalse(diff["diagnostics"]["gitDiffUsed"])

    def test_api_removal_is_high_impact(self) -> None:
        api = {"method": "DELETE", "route": "/api/devices/{id}", "signature": "DELETE:204"}
        diff = self.build(_snapshot("snapshot-1", apis=[api]), _snapshot("snapshot-2"))

        self.assertEqual(diff["removedAPIs"][0]["name"], "DELETE /api/devices/{id}")
        self.assertEqual(diff["impact"]["level"], "High")

    def test_module_movement_and_service_movement_are_preserved(self) -> None:
        before_service = {"name": "DeviceHealthService", "path": "src/health/DeviceHealthService.cs", "signature": "v1"}
        after_service = {"name": "DeviceHealthService", "path": "src/devices/DeviceHealthService.cs", "signature": "v1"}
        diff = self.build(
            _snapshot("snapshot-1", services=[before_service]),
            _snapshot("snapshot-2", services=[after_service], diff={"renamed": [{"oldPath": "src/health/HealthModule.cs", "newPath": "src/devices/HealthModule.cs"}]}),
        )

        self.assertEqual(diff["serviceChanges"]["moved"][0]["changeType"], "Moved")
        self.assertEqual(diff["serviceChanges"]["moved"][0]["after"]["path"], "src/devices/DeviceHealthService.cs")
        self.assertEqual(diff["moduleChanges"]["moved"][0]["after"]["path"], "src/devices/HealthModule.cs")

    def test_refactoring_is_taken_from_structured_execution_evidence(self) -> None:
        snapshot = _snapshot("snapshot-1")
        diff = self.build(snapshot, {**snapshot, "snapshotId": "snapshot-2"}, _result({
            "type": "Refactoring",
            "title": "Extract device health evaluator",
            "content": "Behavior is preserved behind the existing service contract.",
            "changeType": "Modified",
            "evidence": ["Provider response explicitly identifies the extraction."],
        }))

        self.assertEqual(diff["refactoringChanges"]["modified"][0]["name"], "Extract device health evaluator")
        self.assertEqual(diff["impact"]["level"], "Medium")

    def test_architecture_replacement_is_high_impact(self) -> None:
        diff = self.build(
            _snapshot("snapshot-1", architecture=["Layered controller-service-repository architecture"]),
            _snapshot("snapshot-2", architecture=["Hexagonal ports and adapters architecture"]),
        )

        self.assertEqual(len(diff["architectureChanges"]["added"]), 1)
        self.assertEqual(len(diff["architectureChanges"]["removed"]), 1)
        self.assertEqual(diff["impact"]["level"], "High")

    def test_documentation_only_change_stays_low_impact(self) -> None:
        before = _snapshot("snapshot-1", files=[{"path": "README.md", "contentHash": "readme-v1"}])
        after = _snapshot("snapshot-2", files=[
            {"path": "README.md", "contentHash": "readme-v1"},
            {"path": "docs/device-health.md", "contentHash": "docs-v1"},
        ])

        diff = self.build(before, after)

        self.assertEqual(diff["documentationChanges"]["added"][0]["name"], "docs/device-health.md")
        self.assertEqual(diff["impact"]["level"], "Low")
        self.assertEqual(diff["summary"]["categoryCounts"]["configuration"], 0)

    def test_configuration_only_change_is_detected_without_code_claims(self) -> None:
        before = _snapshot("snapshot-1", files=[{"path": "config/device-health.json", "contentHash": "config-v1"}])
        after = _snapshot("snapshot-2", files=[{"path": "config/device-health.json", "contentHash": "config-v2"}])

        diff = self.build(before, after)

        self.assertEqual(diff["configurationChanges"]["modified"][0]["name"], "config/device-health.json")
        self.assertEqual(diff["impact"]["level"], "Medium")
        self.assertEqual(diff["newAPIs"], [])

    def test_dependency_graph_changes_are_reported(self) -> None:
        before_graph = {
            "nodes": [{"id": "controller", "name": "HealthController", "type": "Controller"}],
            "relationships": [],
        }
        after_graph = {
            "nodes": [
                {"id": "controller", "name": "HealthController", "type": "Controller"},
                {"id": "service", "name": "DeviceHealthService", "type": "Service"},
            ],
            "relationships": [{"from": "controller", "to": "service", "type": "uses"}],
        }
        diff = self.build(_snapshot("snapshot-1", graph=before_graph), _snapshot("snapshot-2", graph=after_graph))

        self.assertEqual(len(diff["dependencyGraphChanges"]["nodesAdded"]), 1)
        self.assertEqual(len(diff["dependencyGraphChanges"]["edgesAdded"]), 1)
        self.assertTrue(any("dependency graph" in reason for reason in diff["impact"]["reasons"]))

    def test_persistence_events_api_and_failure_contract(self) -> None:
        router = build_engineering_diff_router(self.service)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {("POST", "/engineering-diff"), ("GET", "/engineering-diff/{diff_id}")})
        payload = {
            "repositorySnapshotBefore": _snapshot("snapshot-1"),
            "repositorySnapshotAfter": _snapshot("snapshot-2", modules=["Device Health"]),
            "executionResult": _result(),
        }

        created = routes[("POST", "/engineering-diff")](payload)
        loaded = routes[("GET", "/engineering-diff/{diff_id}")](created["diffId"])

        self.assertEqual(loaded, created)
        event = self.platform.events.list_recent(event_type="EngineeringDiffCompleted")["events"][0]
        self.assertEqual(event["correlationId"], "corr-engineering-diff-53")
        self.assertEqual(event["payload"]["engineeringDiffId"], created["diffId"])
        with self.assertRaises(HTTPException):
            routes[("POST", "/engineering-diff")]({"repositorySnapshotBefore": {}})
        self.assertEqual(self.platform.events.list_recent(event_type="EngineeringDiffFailed")["count"], 1)

    def test_engine_has_no_git_provider_or_repository_write_authority(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "execution_runtime" / "comparison"
        forbidden = ("subprocess", "git ", "GitPython", "backend.refinement.provider", "RepositoryScanner", "AdoClient")
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, source, f"{path} contains forbidden Engineering Diff authority {marker}")


if __name__ == "__main__":
    unittest.main()
