from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.execution_runtime import (
    PRCandidateGenerator,
    PRCandidateRepository,
    PRCandidateService,
    build_pr_candidate_router,
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


def _change(name: str, path: str = "", change_type: str = "Modified", confidence: float = 0.92) -> dict:
    before = {"name": name, "path": path, "module": "Device Health"} if change_type != "Added" else None
    after = {"name": name, "path": path, "module": "Device Health"} if change_type != "Removed" else None
    return {
        "changeType": change_type,
        "name": name,
        "before": before,
        "after": after,
        "confidence": confidence,
        "reason": f"{name} was {change_type.casefold()} in the repository snapshot.",
        "evidence": [f"Repository evidence for {name}."],
    }


def _diff(*, changes: dict[str, list[dict]] | None = None, impact: str = "Low", diff_id: str = "engineering-diff-57") -> dict:
    value = {
        "diffId": diff_id,
        "sessionId": "execution-session-57",
        "correlationId": "corr-pr-candidate-57",
        "confidence": 0.92,
        "impact": {"level": impact, "score": 10, "reasons": [f"{impact} semantic change impact."]},
        "dependencyGraphChanges": {
            "nodesAdded": [], "nodesRemoved": [], "nodesModified": [],
            "edgesAdded": [], "edgesRemoved": [], "edgesModified": [],
        },
    }
    for field in CHANGE_FIELDS.values():
        value[field] = _empty_changes()
    for change_type, records in (changes or {}).items():
        value[CHANGE_FIELDS[change_type]]["modified"].extend(records)
    return value


def _validation(*, status: str = "Passed", acceptance_score: int = 100) -> dict:
    return {
        "reportId": "validation-result-57",
        "sessionId": "execution-session-57",
        "correlationId": "corr-pr-candidate-57",
        "status": status,
        "confidence": 0.91,
        "acceptanceCoverageScore": acceptance_score,
        "testCoverageScore": 88,
        "acceptanceResults": [
            {"acceptanceCriteriaId": "AC-1", "status": "Implemented", "evidence": ["Device health response test passed."]},
            {"acceptanceCriteriaId": "AC-2", "status": "Implemented", "evidence": ["Permission test passed."]},
        ],
        "violations": [],
        "warnings": [],
    }


def _qa(*, status: str = "Ready", missing: list[str] | None = None) -> dict:
    return {
        "reportId": "qa-result-57",
        "status": status,
        "confidence": 0.9,
        "tests": [
            {"testId": "TC-1", "category": "Integration", "title": "Returns device health"},
            {"testId": "TC-2", "category": "Permission", "title": "Restricts device health access"},
        ],
        "missingTests": missing or [],
        "risks": [],
    }


def _manifest(*, objective: str = "Update device health status", mode: str = "Implement", risks: list[str] | None = None) -> dict:
    return {
        "manifestId": "execution-manifest-57",
        "sourcePackageId": "execution-package-57",
        "sourceVersions": {"repositorySnapshotVersion": "snapshot-57"},
        "objective": objective,
        "businessGoal": "Help Operations Users identify unhealthy devices sooner.",
        "acceptanceCriteria": [
            {"id": "AC-1", "text": "Device health status is returned."},
            {"id": "AC-2", "text": "Unauthorized access is rejected."},
        ],
        "implementationGuidance": {"executionMode": mode},
        "risks": risks or [],
        "confidence": 0.93,
    }


class PRCandidateGeneratorMilestone57Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = PRCandidateService(
            PRCandidateRepository(JsonMapStore(self.root / "pr-candidates.json")),
            platform=self.platform,
        )
        self.generator = PRCandidateGenerator()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def generate(self, diff: dict, *, validation: dict | None = None, qa: dict | None = None, manifest: dict | None = None) -> dict:
        return self.generator.generate(diff, validation or _validation(), qa or _qa(), manifest or _manifest())

    def test_small_change_has_precise_files_modules_acceptance_and_tests(self) -> None:
        diff = _diff(changes={
            "Module": [_change("Device Health", "src/device-health/DeviceHealthModule.cs")],
            "Service": [_change("DeviceHealthService", "src/device-health/DeviceHealthService.cs")],
        })

        candidate = self.generate(diff)

        self.assertEqual(candidate["candidateType"], "Small Change")
        self.assertEqual(candidate["summary"]["title"], "Update device health status")
        self.assertEqual(len(candidate["filesChanged"]), 2)
        self.assertEqual(candidate["modules"][0]["name"], "Device Health")
        self.assertEqual(candidate["acceptanceCoverage"]["score"], 100)
        self.assertEqual(candidate["testingSummary"]["testCount"], 2)
        self.assertEqual(candidate["status"], "Draft")

    def test_large_feature_reports_breaking_migration_architecture_and_release_notes(self) -> None:
        changes = {
            "API": [_change(f"API-{index}", f"src/api/Controller{index}.cs") for index in range(3)],
            "Service": [_change(f"Service-{index}", f"src/services/Service{index}.cs") for index in range(2)],
            "Database": [_change("DeviceHealth migration", "db/migrations/057_device_health.sql")],
            "Architecture": [_change("Device health query boundary", "docs/architecture/device-health.md")],
            "BreakingChange": [_change("Retire legacy health API", "src/api/LegacyHealthController.cs", "Removed")],
        }
        candidate = self.generate(_diff(changes=changes, impact="Critical"), manifest=_manifest(risks=["Legacy API consumers require migration."]))

        self.assertEqual(candidate["candidateType"], "Large Feature")
        self.assertTrue(candidate["breakingChanges"])
        self.assertTrue(candidate["migrationNotes"])
        self.assertTrue(candidate["architectureNotes"])
        self.assertTrue(any("breaking" in note for note in candidate["releaseNotes"]))
        self.assertIn("Legacy API consumers require migration.", candidate["risks"])

    def test_refactor_is_classified_without_claiming_feature_behavior(self) -> None:
        candidate = self.generate(
            _diff(changes={"Refactoring": [_change("Extract device health evaluator", "src/device-health/DeviceHealthEvaluator.cs")]}),
            manifest=_manifest(objective="Preserve behavior while simplifying device health evaluation", mode="Refactor"),
        )

        self.assertEqual(candidate["candidateType"], "Refactor")
        self.assertEqual(candidate["diagnostics"]["changeCounts"]["Refactoring"], 1)
        self.assertEqual(candidate["breakingChanges"], [])

    def test_bug_fix_is_classified_from_execution_manifest(self) -> None:
        candidate = self.generate(
            _diff(changes={"Service": [_change("DeviceHealthService", "src/device-health/DeviceHealthService.cs")]}),
            manifest=_manifest(objective="Fix duplicate offline-device status updates", mode="Bug Fix"),
        )

        self.assertEqual(candidate["candidateType"], "Bug Fix")
        self.assertIn("Bug Fix", candidate["releaseNotes"][0])

    def test_documentation_only_candidate_contains_no_invented_code_files(self) -> None:
        candidate = self.generate(_diff(changes={
            "Documentation": [_change("Device health runbook", "docs/device-health-runbook.md", "Added")],
        }))

        self.assertEqual(candidate["candidateType"], "Documentation")
        self.assertEqual([item["path"] for item in candidate["filesChanged"]], ["docs/device-health-runbook.md"])
        self.assertEqual(candidate["modules"], [])
        self.assertEqual(candidate["migrationNotes"], [])
        self.assertEqual(candidate["architectureNotes"], [])

    def test_missing_file_paths_are_warned_not_invented(self) -> None:
        candidate = self.generate(_diff(changes={"API": [_change("GET /device-health")]}))

        self.assertEqual(candidate["filesChanged"], [])
        self.assertIn("no changed file paths", candidate["warnings"][0])
        self.assertLess(candidate["confidence"], 0.92)

    def test_failed_validation_and_qa_mark_candidate_blocked(self) -> None:
        candidate = self.generate(
            _diff(changes={"Service": [_change("DeviceHealthService", "src/DeviceHealthService.cs")]}),
            validation=_validation(status="Failed", acceptance_score=25),
            qa=_qa(status="Blocked", missing=["Permission regression test"]),
        )

        self.assertEqual(candidate["status"], "Blocked")
        self.assertEqual(candidate["acceptanceCoverage"]["status"], "Partially Covered")
        self.assertTrue(candidate["warnings"])
        self.assertEqual(candidate["testingSummary"]["missingTests"], ["Permission regression test"])

    def test_service_persists_candidate_and_publishes_event_without_creating_pr(self) -> None:
        candidate = self.service.generate({
            "engineeringDiff": _diff(changes={"Service": [_change("DeviceHealthService", "src/DeviceHealthService.cs")]}),
            "validationResult": _validation(),
            "qaResult": _qa(),
            "executionManifest": _manifest(),
        })

        self.assertEqual(self.service.get(candidate["candidateId"]), candidate)
        self.assertFalse(candidate["created"])
        self.assertEqual(candidate["pullRequestId"], "")
        self.assertEqual(candidate["diagnostics"]["gitOperations"], 0)
        self.assertEqual(candidate["diagnostics"]["azureDevOpsWrites"], 0)
        self.assertEqual(candidate["diagnostics"]["pullRequestsCreated"], 0)
        events = self.platform.events.list_recent(event_type="PRCandidateCreated")
        self.assertEqual(events["count"], 1)
        self.assertEqual(events["events"][0]["correlationId"], "corr-pr-candidate-57")
        self.assertFalse(events["events"][0]["payload"]["created"])

    def test_api_contract_and_generator_have_no_pr_transport_dependency(self) -> None:
        router = build_pr_candidate_router(self.service)
        routes = {(next(iter(route.methods)), route.path) for route in router.routes}

        self.assertEqual(routes, {
            ("POST", "/pr-candidates/generate"),
            ("GET", "/pr-candidates"),
            ("GET", "/pr-candidates/{candidate_id}"),
        })
        source = (Path(__file__).parents[1] / "backend" / "execution_runtime" / "pr" / "candidate_service.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("import git", source.casefold())
        self.assertNotIn("from git", source.casefold())
        self.assertNotIn("Popen", source)
        self.assertNotIn("PRReviewEngine", source)
        self.assertNotIn("AzureDevOps", source)


if __name__ == "__main__":
    unittest.main()
