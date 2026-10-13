from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from backend.execution_manifest import ExecutionManifestBuilder
from backend.model_adapters import ModelAdapterCompiler
from backend.model_registry import ModelRegistry
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore
from backend.prompt_compiler import PromptCompiler
from backend.prompt_diagnostics import PromptDiagnosticsBuilder, PromptDiagnosticsService, build_prompt_diagnostics_router
from backend.prompt_optimizer import PromptOptimizer
from backend.token_intelligence import TokenBudgetEngine
from tests.test_execution_manifest_milestone_4_1 import _package


def _artifacts() -> tuple[dict, dict, dict]:
    package = _package()
    package["diagnostics"]["rejectedContext"] = [{
        "candidate": {"category": "File", "path": "src/firmware/FirmwareRolloutService.cs", "confidence": 0.22},
        "reason": "Firmware is outside the approved fault-details scope.",
    }]
    manifest = ExecutionManifestBuilder().build(package)
    compiled = PromptCompiler().compile(manifest)
    bounded = TokenBudgetEngine().optimize(compiled, budget_tokens=2048)
    execution = ModelAdapterCompiler().compile(bounded, "codex")
    optimized = PromptOptimizer().optimize(execution, "implementation")
    return package, manifest, optimized


class PromptDiagnosticsMilestone47Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = PromptDiagnosticsService(
            JsonMapStore(self.root / "prompt-diagnostics.json"),
            model_registry=ModelRegistry(),
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_diagnostics_explain_complete_prompt_lineage_and_model(self) -> None:
        package, manifest, prompt = _artifacts()
        result = self.service.build(prompt, manifest, package)

        self.assertEqual(result["executionManifestVersion"], "1.0")
        self.assertEqual(result["executionPackageVersion"], "2.0")
        self.assertEqual(result["repositorySnapshot"], "snapshot-v7")
        self.assertEqual(result["knowledgeVersion"], "knowledge-v5")
        self.assertEqual(result["memoryVersion"], "memory-v1")
        self.assertEqual(result["model"]["id"], "codex")
        self.assertEqual(result["model"]["name"], "Codex")
        self.assertEqual(result["model"]["provider"], "OpenAI")
        self.assertGreater(result["promptSize"]["characters"], 0)
        self.assertGreater(result["tokenCount"]["estimated"], 0)
        self.assertGreater(result["optimizationRatio"], 0)
        self.assertEqual(result["confidence"], prompt["promptConfidence"])

    def test_files_included_and_excluded_have_reasons(self) -> None:
        package, manifest, prompt = _artifacts()
        result = PromptDiagnosticsBuilder().build(prompt, manifest, package, ModelRegistry().get("codex"))

        self.assertEqual(result["filesIncluded"][0]["path"], "src/fault/FaultEventController.cs")
        self.assertTrue(result["filesIncluded"][0]["reason"])
        excluded = next(item for item in result["filesExcluded"] if "FirmwareRolloutService" in item["path"])
        self.assertIn("outside the approved", excluded["reason"])
        self.assertEqual(excluded["source"], "execution_package.rejectedContext")

    def test_cost_and_duration_are_truthfully_unavailable_without_baselines(self) -> None:
        package, manifest, prompt = _artifacts()
        result = PromptDiagnosticsBuilder().build(prompt, manifest, package, ModelRegistry().get("codex"))

        self.assertEqual(result["estimatedCost"]["status"], "Unavailable")
        self.assertIsNone(result["estimatedCost"]["amount"])
        self.assertEqual(result["estimatedDuration"]["status"], "Unavailable")
        self.assertIsNone(result["estimatedDuration"]["milliseconds"])

    def test_supplied_pricing_and_throughput_enable_deterministic_estimates(self) -> None:
        package, manifest, prompt = _artifacts()
        profile = {
            "inputCostPerMillionTokens": 1.5,
            "outputCostPerMillionTokens": 4.0,
            "expectedOutputTokens": 300,
            "tokensPerSecond": 50,
            "currency": "USD",
        }
        result = PromptDiagnosticsBuilder().build(prompt, manifest, package, ModelRegistry().get("codex"), profile)

        expected_cost = round(prompt["estimatedTokens"] / 1_000_000 * 1.5 + 300 / 1_000_000 * 4.0, 6)
        expected_duration = round((prompt["estimatedTokens"] + 300) / 50 * 1000)
        self.assertEqual(result["estimatedCost"]["amount"], expected_cost)
        self.assertEqual(result["estimatedDuration"]["milliseconds"], expected_duration)

    def test_diagnostics_are_content_addressed_immutable_and_reusable(self) -> None:
        package, manifest, prompt = _artifacts()
        first = self.service.build(prompt, manifest, package)
        second = self.service.build(prompt, manifest, package)

        self.assertEqual(first["diagnosticsId"], second["diagnosticsId"])
        self.assertEqual(first["immutableHash"], second["immutableHash"])
        first["warnings"].append("caller mutation")
        self.assertNotIn("caller mutation", self.service.get(second["diagnosticsId"])["warnings"])
        self.assertEqual(self.service.get_by_prompt(prompt["optimizedPromptId"])["diagnosticsId"], second["diagnosticsId"])

    def test_lineage_mismatch_is_rejected(self) -> None:
        package, manifest, prompt = _artifacts()
        mismatched = deepcopy(manifest)
        mismatched["manifestId"] = "execmanifest_other"

        with self.assertRaisesRegex(ValueError, "lineage do not match"):
            PromptDiagnosticsBuilder().build(prompt, mismatched, package, ModelRegistry().get("codex"))

        mismatched_package = deepcopy(package)
        mismatched_package["packageId"] = "execpkg_other"
        mismatched_package["metadata"]["packageId"] = "execpkg_other"
        with self.assertRaisesRegex(ValueError, "Package and Execution Manifest lineage do not match"):
            PromptDiagnosticsBuilder().build(prompt, manifest, mismatched_package, ModelRegistry().get("codex"))

    def test_api_builds_from_ids_and_exposes_full_summary_and_prompt_lookup(self) -> None:
        package, manifest, prompt = _artifacts()

        class ManifestService:
            def get(self, manifest_id: str):
                return manifest if manifest_id == manifest["manifestId"] else None

        class PackageService:
            def get(self, package_id: str):
                return package if package_id == package["packageId"] else None

        router = build_prompt_diagnostics_router(self.service, ManifestService(), PackageService())
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {
            ("POST", "/prompt-diagnostics/build"),
            ("GET", "/prompt-diagnostics/prompts/{optimized_prompt_id}"),
            ("GET", "/prompt-diagnostics/{diagnostics_id}/summary"),
            ("GET", "/prompt-diagnostics/{diagnostics_id}"),
        })
        built = routes[("POST", "/prompt-diagnostics/build")]({"optimizedPrompt": prompt})
        loaded = routes[("GET", "/prompt-diagnostics/{diagnostics_id}")](built["diagnosticsId"])
        summary = routes[("GET", "/prompt-diagnostics/{diagnostics_id}/summary")](built["diagnosticsId"])
        by_prompt = routes[("GET", "/prompt-diagnostics/prompts/{optimized_prompt_id}")](prompt["optimizedPromptId"])
        self.assertEqual(loaded["immutableHash"], built["immutableHash"])
        self.assertEqual(summary["repositorySnapshot"], "snapshot-v7")
        self.assertEqual(by_prompt["diagnosticsId"], built["diagnosticsId"])

    def test_diagnostics_module_has_no_ui_provider_or_context_retrieval_dependency(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "prompt_diagnostics"
        forbidden = (
            "azure-devops-extension", "vscode-extension", "provider_gateway", "phi_provider",
            "backend.repository_intelligence", "backend.engineering_memory", "backend.context_orchestration",
            "from openai", "import openai", "from anthropic", "import requests", "import httpx",
        )
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8").casefold()
            for marker in forbidden:
                self.assertNotIn(marker.casefold(), source, f"{path.name} contains forbidden dependency {marker}")


if __name__ == "__main__":
    unittest.main()
