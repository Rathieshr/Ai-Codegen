from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.execution import ExecutionPackageBuilder, ExecutionRequest
from backend.convergence import ConsumerRequest, ExecutionPackageConsumerService
from backend.platform_hardening.api import RegressionRunRequest, build_platform_hardening_router
from backend.platform_hardening.harness import HEIEndToEndHarness
from backend.platform_hardening.quality import validate_acceptance_criteria
from backend.platform_hardening.scenarios import SCENARIOS
from backend.engineering_memory import EngineeringMemoryEngine


class HEIPlatformHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.harness = HEIEndToEndHarness(Path(self.temp.name))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_five_realistic_scenarios_complete_converged_pipeline(self) -> None:
        runs = [self.harness.run_scenario(item["scenarioId"], repository_mode="KnowledgeSnapshot") for item in SCENARIOS]

        self.assertEqual(len(runs), 5)
        self.assertTrue(all(run["status"] == "Passed" for run in runs))
        for run in runs:
            artifacts = run["artifacts"]
            self.assertTrue(artifacts["contextCapsule"]["capsuleVersion"])
            self.assertEqual(artifacts["executionPackage"]["metadata"]["capsuleVersion"], artifacts["contextCapsule"]["capsuleVersion"])
            self.assertEqual(artifacts["memoryCaptureDraft"]["approvalStatus"], "Draft")
            self.assertEqual(run["retrievalCounts"]["contextOrchestrationRequests"], 1)
            self.assertTrue(all(value <= 1 for key, value in run["retrievalCounts"].items() if key.endswith("Queries")))

    def test_full_device_health_end_to_end_flow(self) -> None:
        run = self.harness.run_scenario("device-health-dashboard", repository_mode="CodeIndexed")

        self.assertEqual(run["status"], "Passed")
        self.assertEqual(
            set(run["artifacts"]),
            {"epic", "capability", "feature", "story", "task", "contextCapsule", "executionPackage", "developerPrompt", "validation", "qa", "memoryCaptureDraft"},
        )
        self.assertEqual(run["artifacts"]["executionPackage"]["repositoryContext"]["repositoryMode"], "CodeIndexed")

    def test_full_alarm_center_end_to_end_flow(self) -> None:
        run = self.harness.run_scenario("alarm-notification-center", repository_mode="KnowledgeSnapshot")

        self.assertEqual(run["status"], "Passed")
        self.assertEqual(len(run["artifacts"]["executionPackage"]["acceptanceMapping"]), 3)
        self.assertTrue(run["artifacts"]["qa"]["negativeTests"])

    def test_capability_diversity_across_unrelated_requirements(self) -> None:
        domain_sets = {item["scenarioId"]: set(item["domains"]) for item in SCENARIOS}

        self.assertEqual(len({tuple(sorted(items)) for items in domain_sets.values()}), len(SCENARIOS))
        self.assertFalse(domain_sets["user-administration"] & {"Telemetry", "Fault Monitoring", "Firmware Management"})
        self.assertFalse(domain_sets["energy-consumption-analytics"] & {"Authentication", "Authorization", "User Management"})

    def test_user_administration_excludes_unrelated_context(self) -> None:
        run = self.harness.run_scenario("user-administration", repository_mode="KnowledgeSnapshot")
        selected = {item["title"] for item in run["artifacts"]["contextCapsule"]["selectedContext"]}

        self.assertFalse({"Firmware", "Telemetry", "Fault Monitoring"} & selected)
        self.assertEqual(run["status"], "Passed")

    def test_repository_modes_enforce_evidence_boundaries(self) -> None:
        indexed = self.harness.run_scenario("device-health-dashboard", repository_mode="CodeIndexed")
        snapshot = self.harness.run_scenario("device-health-dashboard", repository_mode="KnowledgeSnapshot")
        unavailable = self.harness.run_scenario("device-health-dashboard", repository_mode="Unavailable")

        self.assertTrue(indexed["artifacts"]["executionPackage"]["repositoryContext"]["relevantFiles"])
        self.assertFalse(snapshot["artifacts"]["executionPackage"]["repositoryContext"]["relevantFiles"])
        self.assertFalse(snapshot["artifacts"]["executionPackage"]["repositoryContext"]["relevantAPIs"])
        self.assertEqual(unavailable["artifacts"]["executionPackage"]["repositoryContext"]["repositoryMode"], "Unavailable")
        self.assertLess(unavailable["readiness"], indexed["readiness"])
        self.assertLess(
            unavailable["artifacts"]["executionPackage"]["metadata"]["confidence"],
            indexed["artifacts"]["executionPackage"]["metadata"]["confidence"],
        )

    def test_stale_repository_snapshot_produces_warning_and_reduces_readiness(self) -> None:
        fresh = self.harness.run_scenario("device-health-dashboard", repository_mode="CodeIndexed")
        stale = self.harness.run_scenario("device-health-dashboard", repository_mode="CodeIndexed", repository_freshness="Stale")

        self.assertTrue(any("Stale context detected" in warning for warning in stale["warnings"]))
        self.assertEqual(stale["artifacts"]["contextCapsule"]["freshnessStatus"], "Stale")
        self.assertLess(stale["readiness"], fresh["readiness"])

    def test_acceptance_quality_rejects_fragments_duplicates_and_conjunctions(self) -> None:
        report = validate_acceptance_criteria(
            ["Visible", "And user can save", "Authorized users can save changes.", "Authorized users can save changes."],
            ["User Management"],
        )

        self.assertEqual(report["status"], "Rejected")
        issues = {issue for criterion in report["criteria"] for issue in criterion["issues"]}
        self.assertIn("fragment", issues)
        self.assertIn("leading_conjunction", issues)
        self.assertIn("duplicate", issues)

    def test_weak_acceptance_caps_execution_readiness(self) -> None:
        capsule = {
            "capsuleId": "capsule-weak", "capsuleVersion": "3.5", "confidence": 1.0, "freshnessStatus": "Fresh",
            "diagnostics": {"repositoryMode": "CodeIndexed"},
            "artifact": {"id": "story-weak", "title": "Weak story", "acceptanceCriteria": ["Visible"]},
            "acceptanceCriteria": ["Visible"],
            "selectedContext": [
                {"sourceType": "Planning", "category": "Planning", "title": "Weak story", "content": "Weak story", "confidenceScore": 1.0},
                {"sourceType": "Repository", "category": "File", "title": "src/Valid.cs", "content": "direct", "confidenceScore": 1.0},
                {"sourceType": "Repository", "category": "Module", "title": "Valid", "content": "module", "confidenceScore": 1.0},
            ],
        }

        package = ExecutionPackageBuilder().build(capsule, ExecutionRequest("ImplementationPackage", story_id="story-weak"))

        self.assertEqual(package["metadata"]["status"], "Blocked")
        self.assertLessEqual(package["metadata"]["executionReadiness"], 49)

    def test_prompt_budgets_preserve_structure_without_overflow(self) -> None:
        for budget in (1200, 4000, 8000, 16000):
            run = self.harness.run_scenario("alarm-notification-center", repository_mode="CodeIndexed", token_budget=budget)
            prompt = run["artifacts"]["developerPrompt"]
            self.assertLessEqual(prompt["estimatedTokens"], budget)
            self.assertIn("Acceptance Criteria", prompt["finalPrompt"])
            self.assertTrue(prompt["sections"])

    def test_1200_token_budget_completes_without_parse_or_overflow_failure(self) -> None:
        run = self.harness.run_scenario("device-health-dashboard", repository_mode="KnowledgeSnapshot", token_budget=1200)

        self.assertEqual(run["status"], "Passed")
        self.assertLessEqual(run["artifacts"]["developerPrompt"]["estimatedTokens"], 1200)
        self.assertFalse(any("parse" in blocker.casefold() or "overflow" in blocker.casefold() for blocker in run["blockers"]))

    def test_execution_package_and_consumers_keep_strict_context_boundaries(self) -> None:
        run = self.harness.run_scenario("alarm-notification-center", repository_mode="CodeIndexed")
        capsule = run["artifacts"]["contextCapsule"]
        package = run["artifacts"]["executionPackage"]

        self.assertEqual(package["diagnostics"]["capsuleId"], capsule["capsuleId"])
        self.assertFalse(package["diagnostics"]["retrievalPerformed"])
        self.assertFalse(package["diagnostics"]["llmUsed"])
        for consumer in ("DeveloperPrompt", "Validation", "QA"):
            result = ExecutionPackageConsumerService().consume(
                ConsumerRequest(consumer, package, runtime_evidence={"changedFiles": []}, correlation_id=run["correlationId"])
            )
            self.assertEqual(result["consumerDiagnostics"]["packageId"], package["packageId"])
            self.assertEqual(result["consumerDiagnostics"]["contextCapsuleVersion"], capsule["capsuleVersion"])

    def test_memory_capture_consumes_only_approved_execution_outcomes(self) -> None:
        run = self.harness.run_scenario("device-health-dashboard", repository_mode="CodeIndexed")
        package = run["artifacts"]["executionPackage"]
        outcome = ExecutionPackageConsumerService().consume(ConsumerRequest(
            "MemoryCapture",
            package,
            runtime_evidence={"validationResult": {"status": "Approved"}, "qaResult": {"status": "Approved"}},
            correlation_id=run["correlationId"],
        ))

        self.assertEqual(outcome["sourcePackageId"], package["packageId"])
        self.assertEqual(outcome["validationResult"]["status"], "Approved")
        self.assertEqual(outcome["qaResult"]["status"], "Approved")
        self.assertFalse(outcome["contextRebuilt"])

    def test_blocked_modules_remain_excluded_from_allowed_repository_context(self) -> None:
        capsule = {
            "capsuleId": "capsule-blocked", "capsuleVersion": "3.5", "confidence": 0.9, "freshnessStatus": "Fresh",
            "diagnostics": {"repositoryMode": "KnowledgeSnapshot"},
            "artifact": {"id": "story-blocked", "title": "Review alarms", "acceptanceCriteria": ["Operations users can review active alarms."]},
            "acceptanceCriteria": ["Operations users can review active alarms."],
            "selectedContext": [
                {"sourceType": "Planning", "category": "Planning", "title": "Review alarms", "content": "Review active alarms", "confidenceScore": 0.9},
                {"sourceType": "Repository", "category": "Module", "title": "Alarm Management", "content": "approved module", "confidenceScore": 0.9},
            ],
            "rejectedContext": [{"candidate": {"category": "Module", "title": "Firmware Management"}, "reason": "blocked_module"}],
            "selectedStandards": ["Input validation"],
        }

        package = ExecutionPackageBuilder().build(capsule, ExecutionRequest("ImplementationPackage", story_id="story-blocked"))

        self.assertEqual(package["implementationBoundary"]["blockedModules"], ["Firmware Management"])
        self.assertNotIn("Firmware Management", package["implementationBoundary"]["allowedModules"])
        self.assertNotIn("Firmware Management", str(package["implementationGuidance"]["recommendedSequence"]))

    def test_rejected_context_does_not_leak_into_downstream_artifacts(self) -> None:
        run = self.harness.run_scenario("user-administration", repository_mode="KnowledgeSnapshot")
        downstream = str({
            "planning": run["artifacts"]["executionPackage"]["planningContext"],
            "repository": run["artifacts"]["executionPackage"]["repositoryContext"],
            "implementation": run["artifacts"]["executionPackage"]["implementationGuidance"],
            "prompt": run["artifacts"]["developerPrompt"],
            "qa": run["artifacts"]["qa"],
        })

        for excluded in ("Firmware", "Telemetry", "Fault Monitoring"):
            self.assertNotIn(excluded, downstream)

    def test_failure_recovery_records_safe_trace_and_stops_downstream(self) -> None:
        run = self.harness.run_scenario("firmware-rollout-management", failure_stage="ExecutionPackage")
        trace = self.harness.store.trace(run["correlationId"])

        self.assertEqual(run["status"], "Blocked")
        self.assertNotIn("developerPrompt", run["artifacts"])
        self.assertTrue(any(item["stage"] == "ExecutionPackage" and item["status"] == "Failed" for item in trace))
        self.assertTrue(all("Traceback" not in str(item) for item in trace))
        self.assertGreater(self.harness.platform.audit.by_correlation(run["correlationId"])["count"], 0)

    def test_each_converged_stage_can_fail_without_raw_trace_or_downstream_continuation(self) -> None:
        stages = ["Planning", "ContextOrchestration", "ContextCapsule", "ExecutionPackage", "DeveloperPrompt", "Validation", "QA", "MemoryCaptureDraft"]
        for stage in stages:
            run = self.harness.run_scenario("device-health-dashboard", failure_stage=stage)
            trace = self.harness.store.trace(run["correlationId"])
            failed = next(item for item in trace if item["stage"] == stage and item["status"] == "Failed")
            self.assertEqual(run["status"], "Blocked")
            self.assertIn(run["correlationId"], failed["details"]["message"])
            self.assertNotIn("Traceback", str(failed))

    def test_trace_and_regression_dashboard_api_contracts(self) -> None:
        run = self.harness.run_scenario("energy-consumption-analytics", repository_mode="KnowledgeSnapshot")
        router = build_platform_hardening_router(self.harness)
        routes = {getattr(route, "path", ""): route.endpoint for route in router.routes}

        trace = routes["/platform/runs/{correlation_id}/trace"](run["correlationId"])
        summary = routes["/platform/regression/summary"]()
        listed = routes["/platform/regression/runs"](limit=10)
        detail = routes["/platform/regression/runs/{run_id}"](run["runId"])

        self.assertGreater(trace["eventCount"], 0)
        self.assertEqual(summary["totalScenarios"], 1)
        self.assertIn("ContextOrchestration", summary["performanceBaseline"])
        self.assertTrue(summary["performanceBaseline"]["ContextOrchestration"]["withinTarget"])
        self.assertEqual(listed["count"], 1)
        self.assertEqual(detail["runId"], run["runId"])

    def test_correlation_and_lineage_survive_the_full_lifecycle_trace(self) -> None:
        run = self.harness.run_scenario("device-health-dashboard", repository_mode="CodeIndexed")
        trace = self.harness.store.trace(run["correlationId"])
        completed = {item["stage"]: item for item in trace if item["status"] == "Completed"}
        capsule_id = run["artifacts"]["contextCapsule"]["capsuleId"]
        package_id = run["artifacts"]["executionPackage"]["packageId"]

        self.assertTrue(all(item["correlationId"] == run["correlationId"] for item in trace))
        self.assertEqual(completed["ContextOrchestration"]["details"]["capsuleId"], capsule_id)
        self.assertEqual(completed["ContextCapsule"]["details"]["capsuleId"], capsule_id)
        self.assertEqual(completed["ExecutionPackage"]["details"]["packageId"], package_id)
        for stage in ("DeveloperPrompt", "Validation", "QA", "MemoryCaptureDraft"):
            self.assertEqual(completed[stage]["details"]["capsuleId"], capsule_id)
            self.assertEqual(completed[stage]["details"]["packageId"], package_id)

    def test_duplicate_context_retrieval_is_detected(self) -> None:
        run = self.harness.run_scenario("alarm-notification-center", repository_mode="KnowledgeSnapshot")

        self.assertEqual(run["retrievalCounts"]["contextOrchestrationRequests"], 1)
        self.assertTrue(all(count == 1 for key, count in run["retrievalCounts"].items() if key.endswith("Queries") and key != "graphQueries"))
        self.assertFalse(any("Duplicate context retrieval" in item["message"] and not item["passed"] for item in run["assertions"]))

    def test_regression_suite_is_stable_across_two_runs(self) -> None:
        first = self.harness.run_all(repository_mode="KnowledgeSnapshot", token_budget=1200)["runs"]
        second = self.harness.run_all(repository_mode="KnowledgeSnapshot", token_budget=1200)["runs"]

        first_outcomes = [(item["scenarioId"], item["status"], item["readiness"], [check["passed"] for check in item["assertions"]]) for item in first]
        second_outcomes = [(item["scenarioId"], item["status"], item["readiness"], [check["passed"] for check in item["assertions"]]) for item in second]
        self.assertEqual(first_outcomes, second_outcomes)

    def test_api_level_run_executes_without_ui(self) -> None:
        router = build_platform_hardening_router(self.harness)
        endpoint = next(route.endpoint for route in router.routes if getattr(route, "path", "") == "/platform/regression/run")

        result = endpoint(RegressionRunRequest(scenarioId="device-health-dashboard", repositoryMode="CodeIndexed", tokenBudget=4000))

        self.assertEqual(result["status"], "Passed")
        self.assertTrue(result["correlationId"])

    def test_memory_capture_rejects_unapproved_failed_and_raw_prompt_sources(self) -> None:
        engine = EngineeringMemoryEngine(Path(self.temp.name) / "memory.json")
        unapproved = engine.store_memory({"title": "Unapproved plan", "source": {"status": "Draft"}})
        failed = engine.store_memory({"title": "Failed implementation", "source": {"status": "Failed"}})
        raw_prompt = engine.store_memory({"title": "Raw prompt", "rawPrompt": "implement everything", "source": {"status": "Validated"}})
        approved = engine.store_memory({"title": "Validated package pattern", "artifactType": "ExecutionPackage", "artifactId": "pkg-1", "source": {"status": "Validated"}})

        self.assertFalse(unapproved["stored"])
        self.assertFalse(failed["stored"])
        self.assertFalse(raw_prompt["stored"])
        self.assertTrue(approved["stored"])
        self.assertEqual(approved["memory"]["approvalStatus"], "Validated")

    def test_memory_duplicate_and_version_provenance_are_preserved(self) -> None:
        engine = EngineeringMemoryEngine(Path(self.temp.name) / "memory-version.json")
        source = {"status": "Validated", "repositorySnapshotVersion": "snapshot-v3"}
        first = engine.store_memory({"title": "Reusable package", "artifactType": "ExecutionPackage", "artifactId": "pkg-1", "source": source})
        duplicate = engine.store_memory({"title": "Reusable package", "artifactType": "ExecutionPackage", "artifactId": "pkg-1", "source": source})
        engine.approve_memory(first["memory"]["id"], actor="approver")
        updated = engine.update_memory(first["memory"]["id"], {"summary": "Updated validated package", "source": source}, actor="hardening")

        self.assertFalse(duplicate["stored"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(updated["memory"]["version"], 2)
        self.assertEqual(updated["memory"]["source"]["repositorySnapshotVersion"], "snapshot-v3")


if __name__ == "__main__":
    unittest.main()
