from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.execution_center import ExecutionCenterService, build_execution_center_router, merge_compatibility_packages
from backend.execution.package_service import ExecutionPackageService
from backend.platform.shared import JsonMapStore


def package(package_id: str = "pkg_1") -> dict:
    return {
        "packageId": package_id,
        "generatedAt": "2026-07-14T08:00:00Z",
        "planningContext": {"story": {"id": "201", "title": "View Device Health"}, "task": {}},
        "metadata": {"packageId": package_id, "status": "Ready", "repositorySnapshotVersion": "snapshot-3", "generatedAt": "2026-07-14T08:00:00Z"},
        "diagnostics": {"warnings": []},
    }


def runtime(status: str = "Completed") -> dict:
    return {
        "sessionId": "session_1", "executionPackageVersion": "pkg_1", "executionPlanVersion": "manifest_1",
        "executionPromptId": "prompt_1", "provider": "Azure OpenAI", "model": "gpt-5", "status": status,
        "startedAt": "2026-07-14T08:03:00Z", "completedAt": "2026-07-14T08:05:00Z" if status == "Completed" else "",
        "duration": 120000, "correlationId": "corr_1", "repositorySnapshotVersion": "snapshot-3",
        "attempt": 1, "warnings": [], "diagnostics": {"recoverable": status in {"Failed", "Cancelled"}},
    }


def service(runtime_status: str = "Completed", retry=None) -> ExecutionCenterService:
    return ExecutionCenterService(
        package_provider=lambda: {"pkg_1": package()},
        plan_provider=lambda: {"manifest_1": {"manifestId": "manifest_1", "sourcePackageId": "pkg_1", "manifestVersion": "1", "generatedAt": "2026-07-14T08:01:00Z", "diagnostics": {}}},
        prompt_provider=lambda: {"prompt_1": {"compiledPromptId": "prompt_1", "executionManifestId": "manifest_1", "sourcePackageId": "pkg_1", "compilerVersion": "1", "compiledAt": "2026-07-14T08:02:00Z", "diagnostics": {}}},
        runtime_provider=lambda: {"session_1": runtime(runtime_status)},
        validation_provider=lambda: {"validation_1": {"decisionId": "validation_1", "decision": "Required", "sourceLineage": {"sessionId": "session_1", "correlationId": "corr_1"}, "decidedAt": "2026-07-14T08:06:00Z"}},
        qa_provider=lambda: {"qa_1": {"planId": "qa_1", "decision": "Required", "sessionId": "session_1", "generatedAt": "2026-07-14T08:07:00Z"}},
        memory_provider=lambda: {"candidates": [{"candidateId": "memory_1", "approvalStatus": "Pending", "sourceLineage": {"sessionId": "session_1"}, "createdAt": "2026-07-14T08:08:00Z"}]},
        pr_provider=lambda: {"candidates": [{"candidateId": "pr_1", "status": "Draft", "sourceLineage": {"sessionId": "session_1"}}]},
        retry_runtime=retry,
    )


class ExecutionCenterTests(unittest.TestCase):
    def test_legacy_project_intelligence_packages_are_projected_without_rebuild(self):
        legacy = [{
            "artifact_type": "Execution Package",
            "payload": {"context": {"execution_package_v2": package("pkg_existing")}},
        }]

        result = merge_compatibility_packages({}, legacy)

        self.assertEqual("pkg_existing", result["pkg_existing"]["packageId"])

    def test_registered_compatibility_package_is_visible_before_runtime_starts(self):
        with TemporaryDirectory() as directory:
            packages = ExecutionPackageService(JsonMapStore(Path(directory) / "execution_packages.json"))
            packages.register(package("pkg_compat"), "corr_compat")
            center = ExecutionCenterService(
                package_provider=packages.store.read,
                plan_provider=lambda: {},
                prompt_provider=lambda: {},
                runtime_provider=lambda: {},
            )

            result = center.list()

            self.assertEqual(1, result["summary"]["total"])
            self.assertEqual("pkg_compat", result["items"][0]["id"])
            self.assertEqual("Prompt Generation", result["items"][0]["currentStage"])

    def test_successful_execution_is_fully_traceable(self):
        result = service().get("pkg_1")
        self.assertEqual("Completed", result["status"])
        self.assertEqual("Completed", result["currentStage"])
        self.assertEqual(
            ["Planning", "Planning Pack", "Execution Package", "Prompt Generation", "AI Runtime", "Validation", "QA", "Memory Candidate", "PR Intelligence", "Completed"],
            [stage["stage"] for stage in result["timeline"]],
        )
        self.assertTrue(all(stage["status"] == "Completed" for stage in result["timeline"]))
        self.assertTrue(all("responsibleAgent" in stage and "correlationId" in stage and "diagnostics" in stage and "logs" in stage for stage in result["timeline"]))
        self.assertEqual("pr_1", result["prCandidate"]["id"])
        self.assertEqual("Azure OpenAI", result["executionDetails"]["provider"])

    def test_failed_execution_marks_runtime_and_supports_diagnostics(self):
        result = service("Failed").get("pkg_1")
        self.assertEqual("Failed", result["status"])
        self.assertEqual("AI Runtime", result["currentStage"])
        runtime_stage = next(stage for stage in result["timeline"] if stage["stage"] == "AI Runtime")
        self.assertEqual("Failed", runtime_stage["status"])
        diagnostics = service("Failed").diagnostics("pkg_1")
        self.assertEqual("session_1", diagnostics["lineage"]["sessionId"])

    def test_retry_delegates_to_runtime_without_reimplementing_recovery(self):
        calls = []

        def retry(session_id: str, reason: str):
            calls.append((session_id, reason))
            return {"sessionId": session_id, "status": "AwaitingResponse", "attempt": 2}

        result = service("Failed", retry=retry).retry("pkg_1", "Transient provider failure")
        self.assertEqual("AwaitingResponse", result["status"])
        self.assertEqual([("session_1", "Transient provider failure")], calls)

    def test_cancelled_execution_is_visible_and_recoverable(self):
        result = service("Cancelled").get("session_1")
        self.assertEqual("Cancelled", result["status"])
        self.assertTrue(result["runtime"]["recoverable"])
        self.assertEqual("Cancelled", next(stage for stage in result["timeline"] if stage["stage"] == "AI Runtime")["status"])

    def test_execution_center_api_contract(self):
        app = FastAPI()
        app.include_router(build_execution_center_router(service()))
        client = TestClient(app)
        self.assertEqual(200, client.get("/execution").status_code)
        self.assertEqual("pkg_1", client.get("/execution/pkg_1").json()["id"])
        self.assertEqual(10, len(client.get("/execution/pkg_1/timeline").json()["timeline"]))
        self.assertEqual("corr_1", client.get("/execution/pkg_1/diagnostics").json()["correlationId"])
        self.assertEqual(404, client.get("/execution/missing").status_code)

    def test_execution_center_ui_exposes_observable_lifecycle(self):
        source = (Path(__file__).resolve().parents[1] / "azure-devops-extension/src/executionCenter.tsx").read_text()
        for label in (
            "Execution Timeline", "Start Time", "End Time", "Duration", "Responsible Agent",
            "Correlation ID", "Logs", "Diagnostics", "Prompt Used", "Provider", "Files Changed",
            "Validation Score", "QA Summary", "Generated PR Summary", "Memory Candidate",
        ):
            self.assertIn(label, source)
        self.assertIn("Retry ${stage.stage}", source)


if __name__ == "__main__":
    unittest.main()
