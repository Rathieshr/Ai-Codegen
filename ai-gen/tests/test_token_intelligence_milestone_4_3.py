from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fastapi import HTTPException

from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore
from backend.prompt_compiler import PromptCompiler
from backend.token_intelligence import (
    SUPPORTED_TOKEN_BUDGETS,
    TokenBudgetEngine,
    TokenIntelligenceService,
    build_token_intelligence_router,
)
from tests.test_prompt_compiler_milestone_4_2 import _manifest


def _section(prompt: dict, section_id: str) -> dict:
    return next(section for section in prompt["sections"] if section["id"] == section_id)


class TokenIntelligenceMilestone43Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = TokenIntelligenceService(JsonMapStore(self.root / "budgeted.json"), platform=self.platform)
        self.compiled = PromptCompiler().compile(_manifest())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_all_required_budgets_are_supported(self) -> None:
        self.assertEqual(SUPPORTED_TOKEN_BUDGETS, (1024, 2048, 4096, 8192, 16000, 32000, 128000))
        for budget in SUPPORTED_TOKEN_BUDGETS:
            result = TokenBudgetEngine().optimize(self.compiled, budget_tokens=budget)
            self.assertEqual(result["requestedBudgetTokens"], budget)
            self.assertGreater(result["reservedOutputTokens"], 0)
            self.assertEqual(result["inputBudgetTokens"], budget - result["reservedOutputTokens"])

    def test_low_value_context_is_removed_as_whole_json_values(self) -> None:
        manifest = _manifest()
        manifest["qaGuidance"]["suggestedTests"] = [
            {"title": f"Optional generated test {index}", "notes": "x" * 120}
            for index in range(100)
        ]
        manifest["risks"] = [f"Optional risk {index} with supporting background " + "y" * 100 for index in range(60)]
        compiled = PromptCompiler().compile(manifest)
        repository_before = deepcopy(_section(compiled, "repository_context")["content"])
        validation_before = deepcopy(_section(compiled, "validation")["content"])

        result = TokenBudgetEngine().optimize(compiled, budget_tokens=1024)

        self.assertEqual(result["status"], "Ready")
        self.assertLessEqual(result["diagnostics"]["estimatedTokens"], result["inputBudgetTokens"])
        self.assertGreater(result["diagnostics"]["removedContextCount"], 0)
        self.assertEqual(_section(result, "repository_context")["content"], repository_before)
        self.assertEqual(_section(result, "validation")["content"], validation_before)
        self.assertTrue(result["diagnostics"]["jsonIntegrityValid"])
        self.assertFalse(result["diagnostics"]["jsonTruncated"])
        json.loads(json.dumps(result["sections"]))

    def test_acceptance_criteria_repository_and_validation_are_never_removed(self) -> None:
        result = TokenBudgetEngine().optimize(self.compiled, budget_tokens=1024)
        before_validation = _section(self.compiled, "validation")["content"]
        after_validation = _section(result, "validation")["content"]

        self.assertEqual(after_validation["acceptanceCriteria"], before_validation["acceptanceCriteria"])
        self.assertEqual(after_validation["guidance"], before_validation["guidance"])
        self.assertEqual(_section(result, "repository_context")["content"], _section(self.compiled, "repository_context")["content"])
        self.assertTrue(result["diagnostics"]["acceptanceCriteriaPreserved"])
        self.assertTrue(result["diagnostics"]["repositoryEvidencePreserved"])
        self.assertTrue(result["diagnostics"]["validationGuidancePreserved"])

    def test_protected_context_overflow_blocks_without_truncation(self) -> None:
        manifest = _manifest()
        manifest["acceptanceCriteria"] = [
            {
                "acceptanceCriteriaId": f"AC{index:03d}",
                "acceptanceText": "Authorized operations users can inspect complete device health evidence " + "z" * 120,
                "implementationArea": "Device Health",
                "validationExpectation": "Verify permission, negative, boundary, and regression behavior.",
            }
            for index in range(1, 101)
        ]
        compiled = PromptCompiler().compile(manifest)

        result = TokenBudgetEngine().optimize(compiled, budget_tokens=1024)

        self.assertEqual(result["status"], "Blocked")
        self.assertEqual(result["diagnostics"]["blockReason"], "protected_context_exceeds_input_budget")
        self.assertEqual(len(_section(result, "validation")["content"]["acceptanceCriteria"]), 100)
        self.assertTrue(result["diagnostics"]["acceptanceCriteriaPreserved"])
        self.assertFalse(result["diagnostics"]["jsonTruncated"])

    def test_diagnostics_report_estimated_actual_removed_and_remaining_tokens(self) -> None:
        result = TokenBudgetEngine().optimize(self.compiled, budget_tokens=2048, actual_tokens=701)
        diagnostics = result["diagnostics"]

        self.assertGreater(diagnostics["estimatedTokens"], 0)
        self.assertEqual(diagnostics["actualTokens"], 701)
        self.assertEqual(diagnostics["actualTokensSource"], "provider_usage")
        self.assertIsInstance(diagnostics["removedContext"], list)
        self.assertIn("validation", diagnostics["sectionBudgetAllocation"])
        self.assertTrue(diagnostics["sectionBudgetAllocation"]["validation"]["protected"])
        self.assertEqual(diagnostics["remainingBudget"], result["inputBudgetTokens"] - diagnostics["estimatedTokens"])

    def test_invalid_budget_and_reserve_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported token budget"):
            TokenBudgetEngine().optimize(self.compiled, budget_tokens=1200)
        with self.assertRaisesRegex(ValueError, "reservedOutputTokens"):
            TokenBudgetEngine().optimize(self.compiled, budget_tokens=1024, reserved_output_tokens=1024)

    def test_knowledge_snapshot_and_unavailable_repository_remain_truthful(self) -> None:
        for mode in ("Knowledge Snapshot", "Unavailable"):
            compiled = PromptCompiler().compile(_manifest(mode))
            result = TokenBudgetEngine().optimize(compiled, budget_tokens=1024)
            repository = _section(result, "repository_context")["content"]
            self.assertEqual(repository, _section(compiled, "repository_context")["content"])
            self.assertEqual(repository["relevantFiles"], [])

    def test_service_persists_result_and_api_resolves_compiled_prompt(self) -> None:
        class CompilerService:
            def get(inner_self, compiled_prompt_id: str) -> dict | None:
                return self.compiled if compiled_prompt_id == self.compiled["compiledPromptId"] else None

        router = build_token_intelligence_router(self.service, CompilerService())
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {("POST", "/token-intelligence/optimize"), ("GET", "/token-intelligence/{budgeted_prompt_id}")})

        optimized = routes[("POST", "/token-intelligence/optimize")]({
            "compiledPromptId": self.compiled["compiledPromptId"],
            "budgetTokens": 2048,
            "actualTokens": 690,
            "correlationId": "corr-token-intelligence",
        })
        loaded = routes[("GET", "/token-intelligence/{budgeted_prompt_id}")](optimized["budgetedPromptId"])

        self.assertEqual(loaded["immutableHash"], optimized["immutableHash"])
        self.assertGreater(self.platform.events.list_recent(event_type="TokenOptimizationCompleted")["count"], 0)
        with self.assertRaises(HTTPException):
            routes[("POST", "/token-intelligence/optimize")]({"compiledPromptId": "missing", "budgetTokens": 1024})

    def test_engine_has_no_provider_model_formatter_or_llm_dependencies(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "token_intelligence"
        forbidden = ("prompt_budget", "prompt_builder", "phi_provider", "openai", "anthropic", "providercapabilities")
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8").casefold()
            for marker in forbidden:
                self.assertNotIn(marker.casefold(), source, f"{path.name} contains forbidden Token Intelligence dependency {marker}")


if __name__ == "__main__":
    unittest.main()
