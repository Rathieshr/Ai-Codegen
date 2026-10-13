from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.execution_runtime import (
    MemoryCandidateGenerator,
    MemoryCandidateRepository,
    MemoryCandidateService,
    build_memory_candidate_router,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


CHANGE_FIELDS = (
    "apiChanges",
    "moduleChanges",
    "serviceChanges",
    "dependencyChanges",
    "architectureChanges",
    "testChanges",
    "securityChanges",
    "configurationChanges",
    "databaseChanges",
    "documentationChanges",
    "refactoringChanges",
    "breakingChanges",
)


def _changes() -> dict:
    return {"added": [], "modified": [], "removed": [], "moved": []}


def _diff(*, confidence: float = 0.92, architecture: bool = False, diff_id: str = "engineering-diff-56") -> dict:
    value = {
        "diffId": diff_id,
        "sessionId": "execution-session-56",
        "projectId": "GridHub",
        "confidence": confidence,
        "warnings": [],
        "dependencyGraphChanges": {
            "nodesAdded": [], "nodesRemoved": [], "nodesModified": [],
            "edgesAdded": [], "edgesRemoved": [], "edgesModified": [],
        },
    }
    for field in CHANGE_FIELDS:
        value[field] = _changes()
    value["serviceChanges"]["modified"].append({"name": "DeviceHealthService", "confidence": confidence})
    value["apiChanges"]["modified"].append({"name": "GET /device-health", "confidence": confidence})
    if architecture:
        value["architectureChanges"]["modified"].append({"name": "Device health query boundary", "confidence": confidence})
    return value


def _execution(*, confidence: float = 0.93, status: str = "Completed", bug_fix: bool = False) -> dict:
    return {
        "resultId": "execution-result-56",
        "sessionId": "execution-session-56",
        "correlationId": "corr-memory-candidate-56",
        "projectId": "GridHub",
        "status": status,
        "responseType": "BugFix" if bug_fix else "Implementation",
        "confidence": confidence,
        "warnings": [],
        "engineeringArtifacts": [{
            "artifactId": "artifact-device-health",
            "type": "BugFix" if bug_fix else "Code",
            "title": "DeviceHealthService",
            "evidence": ["Validated DeviceHealthService implementation."],
        }],
    }


def _validation(*, confidence: float = 0.91, status: str = "Passed", recommendations: list[str] | None = None) -> dict:
    return {
        "reportId": "validation-result-56",
        "sessionId": "execution-session-56",
        "correlationId": "corr-memory-candidate-56",
        "status": status,
        "confidence": confidence,
        "violations": [],
        "warnings": [],
        "recommendations": recommendations or [],
    }


def _qa(*, confidence: float = 0.9, status: str = "Ready", tests: bool = True) -> dict:
    return {
        "reportId": "qa-result-56",
        "status": status,
        "confidence": confidence,
        "tests": [{"testId": "TC-DEVICE-1", "title": "Returns offline device health"}] if tests else [],
        "gaps": [],
        "recommendations": [],
    }


def _request(**overrides) -> dict:
    value = {
        "projectId": "GridHub",
        "organizationId": "HEI",
        "executionResult": _execution(),
        "validationResult": _validation(),
        "qaResult": _qa(),
        "engineeringDiff": _diff(),
    }
    value.update(overrides)
    return value


class MemoryCandidateGeneratorMilestone56Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.repository = MemoryCandidateRepository(JsonMapStore(self.root / "memory-candidates.json"))
        self.service = MemoryCandidateService(self.repository, platform=self.platform)
        self.generator = MemoryCandidateGenerator()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_validated_outcome_generates_evidence_backed_candidate_types(self) -> None:
        report = self.generator.generate(_execution(), _validation(), _qa(), _diff(architecture=True), project_id="GridHub")
        by_type = {item["candidateType"]: item for item in report["candidates"]}

        self.assertIn("Architecture Decision", by_type)
        self.assertIn("Implementation Pattern", by_type)
        self.assertIn("Reusable Pattern", by_type)
        self.assertIn("Reusable Test", by_type)
        for candidate in by_type.values():
            self.assertGreaterEqual(candidate["confidence"], 0.65)
            self.assertGreaterEqual(candidate["reuseScore"], 0.55)
            self.assertTrue(candidate["approvalRequired"])
            self.assertFalse(candidate["stored"])
            self.assertFalse(candidate["indexed"])

    def test_bug_fix_and_lesson_learned_are_derived_from_explicit_evidence(self) -> None:
        report = self.generator.generate(
            _execution(bug_fix=True),
            _validation(recommendations=["Preserve retry idempotency during device health refresh."]),
            _qa(),
            _diff(),
            project_id="GridHub",
        )
        candidate_types = {item["candidateType"] for item in report["candidates"]}

        self.assertIn("Bug Fix", candidate_types)
        self.assertIn("Lesson Learned", candidate_types)

    def test_duplicate_existing_memory_is_rejected(self) -> None:
        initial = self.service.generate(_request())
        implementation = next(item for item in initial["candidates"] if item["candidateType"] == "Implementation Pattern")
        existing_memory = {
            "id": "memory-existing-device-health",
            "title": implementation["title"],
            "category": implementation["suggestedCategory"],
            "approvalStatus": "Available",
        }
        duplicate_report = self.service.generate(_request(
            engineeringDiff=_diff(diff_id="engineering-diff-duplicate-56"),
            existingMemory=[existing_memory],
        ))
        duplicate = next(item for item in duplicate_report["candidates"] if item["candidateType"] == "Implementation Pattern")

        self.assertEqual(duplicate["status"], "Rejected")
        self.assertTrue(duplicate["duplicateDetection"]["isDuplicate"])
        self.assertEqual(duplicate["duplicateDetection"]["matchedId"], "memory-existing-device-health")
        self.assertEqual(duplicate["eventType"], "MemoryCandidateRejected")

    def test_low_confidence_candidates_are_rejected(self) -> None:
        report = self.generator.generate(
            _execution(confidence=0.2),
            _validation(confidence=0.2),
            _qa(confidence=0.2),
            _diff(confidence=0.2),
            project_id="GridHub",
        )

        self.assertTrue(report["candidates"])
        self.assertTrue(all(item["status"] == "Rejected" for item in report["candidates"]))
        self.assertTrue(all(any("Confidence" in reason for reason in item["rejectionReasons"]) for item in report["candidates"]))

    def test_organization_policy_controls_scope_and_candidate_types(self) -> None:
        policy = {
            "allowOrganizationScope": True,
            "organizationScopeMinimumConfidence": 0.8,
            "organizationScopeMinimumReuseScore": 0.75,
            "blockedCandidateTypes": ["Reusable Pattern"],
        }
        report = self.generator.generate(
            _execution(), _validation(), _qa(), _diff(),
            project_id="GridHub", organization_id="HEI", policy=policy,
        )
        by_type = {item["candidateType"]: item for item in report["candidates"]}

        self.assertEqual(by_type["Reusable Pattern"]["status"], "Rejected")
        self.assertIn("organization policy", " ".join(by_type["Reusable Pattern"]["rejectionReasons"]))
        self.assertTrue(by_type["Implementation Pattern"]["organizationScope"]["eligible"])

    def test_failed_validation_or_qa_cannot_create_memory_candidate(self) -> None:
        report = self.generator.generate(_execution(), _validation(status="Failed"), _qa(status="Blocked"), _diff(), project_id="GridHub")

        self.assertTrue(all(item["status"] == "Rejected" for item in report["candidates"]))
        reasons = " ".join(reason for item in report["candidates"] for reason in item["rejectionReasons"])
        self.assertIn("Validation Result status is failed", reasons)
        self.assertIn("QA Result status is blocked", reasons)

    def test_incomplete_source_status_requires_review_before_candidate_creation(self) -> None:
        report = self.generator.generate(
            _execution(status="InProgress"),
            _validation(status="NeedsReview"),
            _qa(status="Pending"),
            _diff(),
            project_id="GridHub",
        )

        self.assertTrue(all(item["status"] == "Rejected" for item in report["candidates"]))
        reasons = " ".join(reason for item in report["candidates"] for reason in item["rejectionReasons"])
        self.assertIn("only completed, approved, passed, or ready outcomes", reasons)

    def test_approval_workflow_never_stores_or_indexes_memory(self) -> None:
        report = self.service.generate(_request())
        candidate = next(item for item in report["candidates"] if item["status"] == "PendingApproval")

        approved = self.service.approve(candidate["candidateId"], "Engineering Lead")

        self.assertEqual(approved["approvalStatus"], "Approved")
        self.assertEqual(approved["approvedBy"], "Engineering Lead")
        self.assertFalse(approved["stored"])
        self.assertFalse(approved["indexed"])
        with self.assertRaisesRegex(ValueError, "already Approved"):
            self.service.approve(candidate["candidateId"], "Engineering Lead")

    def test_service_publishes_created_and_rejected_events(self) -> None:
        created = self.service.generate(_request())
        rejected = self.service.generate(_request(
            engineeringDiff=_diff(diff_id="engineering-diff-low-56", confidence=0.2),
            executionResult=_execution(confidence=0.2),
            validationResult=_validation(confidence=0.2),
            qaResult=_qa(confidence=0.2),
        ))

        self.assertTrue(created["createdCandidates"])
        self.assertTrue(rejected["rejectedCandidates"])
        self.assertGreater(self.platform.events.list_recent(event_type="MemoryCandidateCreated")["count"], 0)
        self.assertGreater(self.platform.events.list_recent(event_type="MemoryCandidateRejected")["count"], 0)
        event = self.platform.events.list_recent(event_type="MemoryCandidateCreated")["events"][0]
        self.assertEqual(event["correlationId"], "corr-memory-candidate-56")
        self.assertFalse(event["payload"]["stored"])
        self.assertFalse(event["payload"]["indexed"])

    def test_human_rejection_publishes_rejected_event(self) -> None:
        report = self.service.generate(_request())
        candidate = next(item for item in report["candidates"] if item["status"] == "PendingApproval")

        rejected = self.service.reject(candidate["candidateId"], "Architecture Review", "Too project-specific for reuse.")

        self.assertEqual(rejected["approvalStatus"], "Rejected")
        self.assertIn("Too project-specific", rejected["rejectionReasons"][-1])
        self.assertGreater(self.platform.events.list_recent(event_type="MemoryCandidateRejected")["count"], 0)

    def test_api_contract_and_no_memory_writer_dependency(self) -> None:
        router = build_memory_candidate_router(self.service)
        routes = {(next(iter(route.methods)), route.path) for route in router.routes}

        self.assertEqual(routes, {
            ("POST", "/memory-candidates/generate"),
            ("GET", "/memory-candidates"),
            ("GET", "/memory-candidates/{candidate_id}"),
            ("POST", "/memory-candidates/{candidate_id}/approve"),
            ("POST", "/memory-candidates/{candidate_id}/reject"),
        })
        source = (Path(__file__).parents[1] / "backend" / "execution_runtime" / "memory" / "candidate_service.py").read_text(encoding="utf-8")
        self.assertNotIn("MemoryWriter", source)
        self.assertNotIn("EngineeringMemoryEngine", source)


if __name__ == "__main__":
    unittest.main()
