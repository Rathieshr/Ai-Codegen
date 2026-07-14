from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.convergence import ConsumerRequest, ExecutionPackageConsumerService
from backend.execution import ExecutionPackageBuilder, ExecutionRequest
from backend.execution_manifest import ExecutionManifestBuilder, ExecutionManifestService, build_execution_manifest_router
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore
from backend.prompt_builder import compile_execution_manifest


def _package(*, business_goal: str = "Reduce fault investigation time.") -> dict:
    capsule = {
        "capsuleId": "capsule-manifest-1",
        "capsuleVersion": "3.5",
        "knowledgeVersion": "knowledge-v5",
        "planningVersion": "planning-v2",
        "engineeringMemoryVersion": "memory-v1",
        "repositorySnapshotVersion": "snapshot-v7",
        "repositoryMode": "CodeIndexed",
        "confidence": 0.91,
        "freshnessStatus": "Fresh",
        "businessGoal": business_goal,
        "artifact": {
            "id": "story-42",
            "title": "View critical fault details",
            "description": "Allow an Operations User to inspect a critical fault event.",
        },
        "acceptanceCriteria": [
            "Authorized users can view fault severity and device health.",
            "Missing telemetry is shown as unavailable.",
        ],
        "selectedCapabilities": ["Fault Monitoring"],
        "selectedFlows": ["Fault Event Review Flow"],
        "selectedStandards": ["Role-based access", "Structured logging"],
        "suggestedTests": ["Permission test", "Missing telemetry test"],
        "selectedContext": [
            {"sourceType": "Planning", "category": "Planning", "title": "View critical fault details", "content": "Approved story", "confidenceScore": 0.95},
            {"sourceType": "Repository", "category": "File", "title": "src/fault/FaultEventController.cs", "content": "Fault details endpoint", "confidenceScore": 0.92},
            {"sourceType": "Repository", "category": "Module", "title": "Fault Monitoring", "content": "Fault module", "confidenceScore": 0.9},
            {"sourceType": "Repository", "category": "Dependency", "title": "Telemetry Service", "content": "Fault telemetry dependency", "confidenceScore": 0.86},
            {"sourceType": "EngineeringStandards", "category": "Standard", "title": "Role-based access", "content": "Authorization rule", "confidenceScore": 0.9},
        ],
        "diagnostics": {"repositoryMode": "CodeIndexed"},
    }
    return ExecutionPackageBuilder().build(
        capsule,
        ExecutionRequest("ImplementationPackage", story_id="story-42", task_id="task-9", repository_snapshot_version="snapshot-v7"),
    )


class ExecutionManifestFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = ExecutionManifestService(
            JsonMapStore(self.root / "manifests.json"),
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_builder_projects_complete_model_independent_manifest(self) -> None:
        manifest = ExecutionManifestBuilder().build(_package())

        self.assertTrue(manifest["immutable"])
        self.assertEqual(manifest["sourcePackageId"], _package()["packageId"])
        self.assertEqual(manifest["businessGoal"], "Reduce fault investigation time.")
        self.assertEqual(len(manifest["acceptanceCriteria"]), 2)
        self.assertEqual(manifest["relevantFiles"], ["src/fault/FaultEventController.cs"])
        self.assertIn("Telemetry Service", manifest["dependencies"])
        self.assertTrue(manifest["implementationGuidance"])
        self.assertTrue(manifest["validationGuidance"])
        self.assertTrue(manifest["qaGuidance"])
        self.assertGreater(manifest["tokenEstimates"]["manifestTokens"], 0)
        self.assertNotIn("developerPrompt", manifest["tokenEstimates"])
        self.assertTrue(manifest["diagnostics"]["modelIndependent"])
        self.assertFalse(manifest["diagnostics"]["promptFormattingApplied"])
        self.assertFalse(manifest["diagnostics"]["providerSelected"])
        self.assertFalse(manifest["diagnostics"]["llmUsed"])
        self.assertFalse(manifest["diagnostics"]["retrievalPerformed"])

    def test_manifest_identity_is_content_addressed_and_immutable(self) -> None:
        first = self.service.build(_package(), "corr-manifest")
        second = self.service.build(_package(), "corr-manifest")
        self.assertEqual(first["manifestId"], second["manifestId"])

        first["objective"] = "caller mutation"
        stored = self.service.get(second["manifestId"])
        self.assertNotEqual(stored["objective"], "caller mutation")

        changed = self.service.build(_package(business_goal="Improve outage response."))
        self.assertNotEqual(changed["manifestId"], second["manifestId"])

    def test_summary_and_diagnostics_preserve_lineage(self) -> None:
        manifest = self.service.build(_package())
        summary = self.service.summary(manifest["manifestId"])
        diagnostics = self.service.diagnostics(manifest["manifestId"])

        self.assertEqual(summary["sourcePackageId"], manifest["sourcePackageId"])
        self.assertEqual(summary["acceptanceCriteriaCount"], 2)
        self.assertEqual(diagnostics["repositorySnapshotVersion"], "snapshot-v7")
        self.assertEqual(diagnostics["knowledgeVersion"], "knowledge-v5")
        self.assertTrue(diagnostics["immutable"])

    def test_api_contract_exposes_only_build_and_read_routes(self) -> None:
        package = _package()

        class PackageService:
            def get(self, package_id: str) -> dict | None:
                return package if package_id == package["packageId"] else None

        router = build_execution_manifest_router(self.service, PackageService())
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(
            set(routes),
            {
                ("POST", "/execution-manifests/build"),
                ("GET", "/execution-manifests/{manifest_id}"),
                ("GET", "/execution-manifests/{manifest_id}/summary"),
                ("GET", "/execution-manifests/{manifest_id}/diagnostics"),
            },
        )
        manifest = routes[("POST", "/execution-manifests/build")]({"executionPackageId": package["packageId"]})
        loaded = routes[("GET", "/execution-manifests/{manifest_id}")](manifest["manifestId"])
        self.assertEqual(loaded["immutableHash"], manifest["immutableHash"])

    def test_prompt_compiler_is_a_separate_manifest_consumer(self) -> None:
        manifest = self.service.build(_package())
        result = compile_execution_manifest(manifest, provider="azure_phi")

        self.assertEqual(result["manifestId"], manifest["manifestId"])
        self.assertEqual(result["packageId"], manifest["sourcePackageId"])
        self.assertTrue(result["compiledPromptId"].startswith("compiledprompt_"))
        self.assertIn("# Execution Prompt", result["finalPrompt"])
        self.assertIn("Authorized users can view fault severity", result["finalPrompt"])
        self.assertIn("src/fault/FaultEventController.cs", result["finalPrompt"])
        self.assertGreater(result["estimatedTokens"], 0)

    def test_legacy_developer_prompt_consumer_uses_manifest(self) -> None:
        consumer = ExecutionPackageConsumerService(self.platform, self.service)
        result = consumer.consume(ConsumerRequest("DeveloperPrompt", _package(), correlation_id="corr-legacy"))

        self.assertTrue(result["manifestId"].startswith("execmanifest_"))
        self.assertTrue(result["budgetedPromptId"].startswith("budgetedprompt_"))
        self.assertTrue(result["diagnostics"]["tokenIntelligence"]["acceptanceCriteriaPreserved"])
        self.assertIn("# Execution Prompt", result["finalPrompt"])
        self.assertEqual(result["diagnostics"]["contextRetrieved"], False)
        self.assertGreater(self.platform.events.list_recent(event_type="ExecutionManifestBuilt")["count"], 0)

    def test_manifest_module_has_no_prompt_provider_or_context_authority_imports(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "execution_manifest"
        forbidden = (
            "backend.prompt_builder",
            "backend.prompt_budget",
            "backend.refinement.provider",
            "backend.repository_intelligence",
            "backend.engineering_memory",
            "backend.context_orchestration",
        )
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, source, f"{path.name} imports forbidden authority {marker}")


if __name__ == "__main__":
    unittest.main()
