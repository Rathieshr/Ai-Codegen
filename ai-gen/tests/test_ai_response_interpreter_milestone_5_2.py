from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.execution_runtime import (
    ResponseInterpretationRepository,
    ResponseInterpretationService,
    build_response_interpreter_router,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


def _session() -> dict:
    return {
        "sessionId": "execution-session-52",
        "provider": "Unknown Provider",
        "model": "model-1",
        "status": "AwaitingResponse",
        "correlationId": "corr-interpret-52",
        "runtimeContext": {"repositoryId": "repo-gridhub"},
    }


def _manifest() -> dict:
    return {
        "manifestId": "manifest-52",
        "manifestVersion": "1.0",
        "objective": "Implement device health API.",
        "acceptanceCriteria": [{"id": "AC-1", "text": "Offline devices are returned."}],
    }


def _snapshot() -> dict:
    return {
        "snapshotId": "snapshot-52",
        "version": 4,
        "status": "Completed",
        "metadata": {
            "files": [
                {"path": "src/DeviceHealthController.cs"},
                {"path": "tests/DeviceHealthControllerTests.cs"},
                {"path": "docs/device-health.md"},
                {"path": "config/device-health.json"},
            ]
        },
    }


class AIResponseInterpreterMilestone52Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = ResponseInterpretationService(
            ResponseInterpretationRepository(JsonMapStore(self.root / "interpretations.json")),
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def interpret(self, response, *, snapshot=True) -> dict:
        return self.service.interpret({
            "executionSession": _session(),
            "providerResponse": response,
            "executionManifest": _manifest(),
            "repositorySnapshot": _snapshot() if snapshot else None,
        })

    def test_simple_response_extracts_files_symbols_api_notes_and_risk(self) -> None:
        response = """
Modified src/DeviceHealthController.cs.
public class DeviceHealthController {
  public HealthStatus GetHealth() { }
}
GET /api/device-health/{id}
TODO: Add metrics after the initial release.
Risk: Missing telemetry may produce an unknown state.
Architecture Note: Keep the controller dependent on the health service abstraction.
Implementation Note: Preserve existing authorization checks.
"""
        result = self.interpret(response)

        self.assertEqual(result["status"], "Interpreted")
        self.assertTrue(result["extraction"]["files"])
        self.assertEqual(result["extraction"]["classes"][0]["title"], "DeviceHealthController")
        self.assertEqual(result["extraction"]["methods"][0]["title"], "GetHealth")
        self.assertIn("GET /api/device-health/{id}", [item["title"] for item in result["extraction"]["apis"]])
        self.assertTrue(result["extraction"]["todos"])
        self.assertTrue(result["risks"])
        self.assertTrue(result["architectureNotes"])
        self.assertTrue(result["implementationNotes"])
        for artifact in result["engineeringArtifacts"]:
            self.assertGreater(artifact["confidence"], 0)
            self.assertTrue(artifact["evidence"])
            self.assertTrue(artifact["source"])
            self.assertTrue(artifact["reason"])

    def test_large_structured_response_preserves_all_explicit_artifacts(self) -> None:
        files = [{"path": f"src/services/Service{i}.cs", "name": f"Service{i}", "confidence": 0.9} for i in range(250)]
        result = self.interpret({"summary": "Large implementation", "files": files})

        self.assertEqual(len(result["extraction"]["files"]), 250)
        self.assertEqual(result["diagnostics"]["artifactCount"], 250)
        self.assertGreater(result["diagnostics"]["warningCount"], 0)
        self.assertFalse(result["safety"]["fabricatedEvidence"])

    def test_malformed_response_fails_visibly_and_publishes_failure(self) -> None:
        with self.assertRaisesRegex(ValueError, "providerResponse"):
            self.interpret(None)

        events = self.platform.events.list_recent(event_type="ResponseInterpretationFailed")["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["correlationId"], "corr-interpret-52")
        self.assertIsNone(self.service.get("execution-session-52"))

    def test_multiple_file_response_tracks_tests_and_repository_evidence(self) -> None:
        result = self.interpret({
            "summary": "Updated health endpoint.",
            "files": [
                {"path": "src/DeviceHealthController.cs", "changeType": "Modified"},
                {"path": "src/InventedService.cs", "changeType": "Added"},
            ],
            "testsAdded": [{"path": "tests/DeviceHealthControllerTests.cs"}],
            "testsRemoved": ["tests/LegacyHealthTests.cs"],
        })

        file_by_path = {item["path"]: item for item in result["extraction"]["files"]}
        self.assertEqual(file_by_path["src/DeviceHealthController.cs"]["repositoryEvidence"], "Matched")
        self.assertEqual(file_by_path["src/InventedService.cs"]["repositoryEvidence"], "Unverified")
        self.assertEqual(result["extraction"]["testsAdded"][0]["changeType"], "Added")
        self.assertEqual(result["extraction"]["testsRemoved"][0]["changeType"], "Deleted")
        self.assertTrue(any("InventedService.cs" in warning for warning in result["warnings"]))

    def test_mixed_documentation_code_configuration_and_database_response(self) -> None:
        result = self.interpret({
            "artifacts": [{"type": "Code", "path": "src/DeviceHealthController.cs", "content": "class DeviceHealthController {}"}],
            "documentationChanges": [{"path": "docs/device-health.md", "description": "Document health states."}],
            "configurationChanges": [{"path": "config/device-health.json", "description": "Add stale threshold."}],
            "databaseChanges": [{"path": "migrations/004_health.sql", "description": "Add device health state."}],
            "fixmes": ["FIXME: handle legacy null health state."],
            "breakingChanges": ["Breaking Change: health status is now an enum."],
        })

        self.assertTrue(result["extraction"]["documentationChanges"])
        self.assertTrue(result["extraction"]["configurationChanges"])
        self.assertTrue(result["extraction"]["databaseChanges"])
        self.assertTrue(result["extraction"]["fixmes"])
        self.assertTrue(result["extraction"]["breakingChanges"])

    def test_unknown_provider_shape_is_retained_as_needs_review(self) -> None:
        result = self.interpret({"unexpectedProviderPayload": [1, 2, 3]})

        self.assertEqual(result["status"], "NeedsReview")
        self.assertEqual(result["responseType"], "Unknown")
        self.assertEqual(len(result["engineeringArtifacts"]), 1)
        self.assertEqual(result["engineeringArtifacts"][0]["type"], "Unknown")
        self.assertTrue(result["unknownItems"])
        self.assertLess(result["confidence"], 0.3)
        self.assertTrue(any("not recognized" in warning for warning in result["warnings"]))

    def test_repository_unavailable_keeps_provider_claims_unverified(self) -> None:
        result = self.interpret({"files": [{"path": "src/DeviceHealthController.cs"}]}, snapshot=False)

        artifact = result["extraction"]["files"][0]
        self.assertEqual(result["repositoryEvidenceStatus"], "Unavailable")
        self.assertEqual(artifact["repositoryEvidence"], "Unavailable")
        self.assertNotIn("Repository snapshot", " ".join(artifact["evidence"]))
        self.assertTrue(any("unavailable" in warning.casefold() for warning in result["warnings"]))

    def test_events_persistence_and_api_contract(self) -> None:
        router = build_response_interpreter_router(self.service)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {
            ("POST", "/runtime/interpreter/interpret"),
            ("GET", "/runtime/interpreter/{session_id}"),
        })
        result = routes[("POST", "/runtime/interpreter/interpret")]({
            "executionSession": _session(),
            "providerResponse": {"files": [{"path": "src/DeviceHealthController.cs"}]},
            "executionManifest": _manifest(),
            "repositorySnapshot": _snapshot(),
        })
        loaded = routes[("GET", "/runtime/interpreter/{session_id}")]("execution-session-52")
        self.assertEqual(loaded["interpretationId"], result["interpretationId"])
        self.assertEqual(self.platform.events.list_recent(event_type="ResponseInterpreted")["count"], 1)
        self.assertEqual(self.platform.events.list_recent(event_type="ArtifactsExtracted")["count"], 1)
        with self.assertRaises(HTTPException):
            routes[("GET", "/runtime/interpreter/{session_id}")]("missing")

    def test_interpreter_does_not_import_validation_qa_repository_writers_or_providers(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "execution_runtime"
        forbidden = (
            "backend.refinement.provider",
            "backend.implementation_validation",
            "backend.validation",
            "backend.qa",
            "backend.ado",
            "subprocess",
        )
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, source, f"{path} imports forbidden interpreter authority {marker}")


if __name__ == "__main__":
    unittest.main()
