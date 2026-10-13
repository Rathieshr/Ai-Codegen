from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.prompt_intelligence_hardening import (
    PromptIntelligenceHardeningHarness,
    build_prompt_intelligence_hardening_router,
    render_benchmark_markdown,
)
from backend.token_intelligence.models import SUPPORTED_TOKEN_BUDGETS


class PromptIntelligenceHardeningMilestone410Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.harness = PromptIntelligenceHardeningHarness(cls.root)
        cls.report = cls.harness.run()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_large_and_small_repository_scenarios_pass(self) -> None:
        values = {item["id"]: item for item in self.report["repositoryScenarios"]}
        self.assertEqual(values["small-code-indexed"]["status"], "Passed")
        self.assertEqual(values["small-code-indexed"]["fileCount"], 4)
        self.assertEqual(values["large-code-indexed"]["status"], "Passed")
        self.assertEqual(values["large-code-indexed"]["fileCount"], 600)
        self.assertGreater(values["large-code-indexed"]["manifestTokens"], values["small-code-indexed"]["manifestTokens"])

    def test_snapshot_and_unavailable_modes_never_invent_files(self) -> None:
        values = {item["id"]: item for item in self.report["repositoryScenarios"]}
        for scenario_id in ("knowledge-snapshot", "repository-unavailable"):
            value = values[scenario_id]
            self.assertEqual(value["status"], "Passed")
            self.assertEqual(value["fileCount"], 0)
            self.assertTrue(value["evidenceSafe"])
            self.assertTrue(value["repositoryModePreserved"])

    def test_every_registered_model_adapter_passes(self) -> None:
        results = self.report["modelAdapters"]
        self.assertEqual({item["modelId"] for item in results}, {"gpt", "codex", "claude", "gemini", "glm", "qwen", "ollama"})
        self.assertTrue(all(item["status"] == "Passed" for item in results))
        self.assertTrue(all(item["contextLimitRespected"] for item in results))

    def test_all_token_budgets_complete_with_protected_json_intact(self) -> None:
        results = self.report["tokenBudgets"]
        self.assertEqual(tuple(item["budgetTokens"] for item in results), SUPPORTED_TOKEN_BUDGETS)
        self.assertTrue(all(item["status"] == "Passed" for item in results))
        self.assertTrue(all(item["protectedContextPreserved"] for item in results))
        self.assertTrue(all(item["jsonIntegrityValid"] for item in results))
        smallest = next(item for item in results if item["budgetTokens"] == 1024)
        self.assertEqual(smallest["budgetStatus"], "Blocked")

    def test_cache_avoids_repeated_prompt_generation_and_tracks_savings(self) -> None:
        cache = self.report["cache"]
        self.assertEqual(cache["status"], "Passed")
        self.assertEqual(cache["firstStatus"], "Miss")
        self.assertEqual(cache["secondStatus"], "Hit")
        self.assertTrue(cache["sameRoutingId"])
        self.assertEqual(cache["metrics"]["generationsAvoided"], 1)
        self.assertGreater(cache["metrics"]["estimatedTokensSaved"], 0)

    def test_routing_diagnostics_and_regression_are_stable(self) -> None:
        self.assertEqual(self.report["routing"]["status"], "Passed")
        self.assertEqual(self.report["routing"]["passed"], self.report["routing"]["total"])
        self.assertEqual(self.report["diagnostics"]["status"], "Passed")
        self.assertTrue(self.report["diagnostics"]["lineageComplete"])
        self.assertEqual(self.report["regression"]["status"], "Passed")
        self.assertTrue(self.report["regression"]["stable"])

    def test_performance_and_readiness_gates_pass(self) -> None:
        self.assertEqual(self.report["performance"]["status"], "Passed")
        self.assertTrue(all(value["withinTarget"] for value in self.report["performance"]["stages"].values()))
        self.assertEqual(self.report["readiness"]["status"], "Production Ready")
        self.assertEqual(self.report["readiness"]["passedGates"], self.report["readiness"]["totalGates"])
        self.assertEqual(self.report["readiness"]["blockers"], [])

    def test_benchmark_report_is_persisted_and_renderable(self) -> None:
        loaded = self.harness.get(self.report["runId"])
        latest = self.harness.latest()
        markdown = render_benchmark_markdown(self.report)

        self.assertEqual(loaded["runId"], self.report["runId"])
        self.assertEqual(latest["runId"], self.report["runId"])
        self.assertIn("# Prompt Intelligence Benchmark", markdown)
        self.assertIn("Production Ready", markdown)
        self.assertIn("large-code-indexed", markdown)

    def test_hardening_api_runs_and_returns_reports(self) -> None:
        api_root = self.root / "api"
        harness = PromptIntelligenceHardeningHarness(api_root)
        router = build_prompt_intelligence_hardening_router(harness)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {
            ("POST", "/prompt-intelligence/hardening/run"),
            ("GET", "/prompt-intelligence/hardening/report"),
            ("GET", "/prompt-intelligence/hardening/runs/{run_id}"),
        })
        with self.assertRaises(HTTPException) as error:
            routes[("GET", "/prompt-intelligence/hardening/report")]()
        self.assertEqual(error.exception.status_code, 404)
        report = routes[("POST", "/prompt-intelligence/hardening/run")]()
        loaded = routes[("GET", "/prompt-intelligence/hardening/runs/{run_id}")](report["runId"])
        self.assertEqual(loaded["readiness"]["status"], "Production Ready")

    def test_hardening_layer_is_provider_free(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "prompt_intelligence_hardening"
        forbidden = (
            "provider_gateway", "phi_provider", "get_refinement_provider", "from openai", "import openai",
            "from anthropic", "import anthropic", "import requests", "import httpx", "urllib", "aiohttp",
        )
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8").casefold()
            for marker in forbidden:
                self.assertNotIn(marker.casefold(), source, f"{path.name} contains forbidden provider dependency {marker}")


if __name__ == "__main__":
    unittest.main()
