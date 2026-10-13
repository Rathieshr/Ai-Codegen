from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from backend.model_adapters import ModelAdapterCompiler
from backend.prompt_compiler import PromptCompiler
from backend.prompt_optimizer import PromptOptimizer, SUPPORTED_PROMPT_MODES
from backend.token_intelligence import TokenBudgetEngine
from tests.test_prompt_compiler_milestone_4_2 import _manifest


PROTECTED = {"repository_context", "implementation_guidance", "validation"}


def _execution_prompt(repository_mode: str = "CodeIndexed", *, budget: int = 2048, model: str = "codex") -> dict:
    compiled = PromptCompiler().compile(_manifest(repository_mode))
    bounded = TokenBudgetEngine().optimize(compiled, budget_tokens=budget)
    return ModelAdapterCompiler().compile(bounded, model)


def _content(prompt: dict, section_id: str):
    for section in [*prompt.get("sections", []), *prompt.get("appendix", [])]:
        if section.get("id") == section_id:
            return section.get("content")
    return None


class PromptOptimizerMilestone46Tests(unittest.TestCase):
    def test_all_supported_modes_prioritize_protected_engineering_sections(self) -> None:
        optimizer = PromptOptimizer()
        source = _execution_prompt()

        for mode in SUPPORTED_PROMPT_MODES:
            result = optimizer.optimize(source, mode)
            first_three = {section["id"] for section in result["sections"][:3]}
            self.assertEqual(first_three, PROTECTED, mode)
            self.assertEqual(result["mode"], mode)
            self.assertEqual(result["status"], "Ready")
            self.assertIn(mode.replace("_", " ").title(), result["prompt"])

    def test_mode_aliases_are_normalized_and_invalid_mode_fails_visibly(self) -> None:
        optimizer = PromptOptimizer()
        source = _execution_prompt()

        self.assertEqual(optimizer.optimize(source, "Bug Fix")["mode"], "bug_fix")
        self.assertEqual(optimizer.optimize(source, "BUG-FIX")["mode"], "bug_fix")
        with self.assertRaisesRegex(ValueError, "Unsupported prompt mode"):
            optimizer.optimize(source, "deployment")

    def test_repeated_and_similar_instructions_are_merged(self) -> None:
        source = deepcopy(_execution_prompt())
        source["modelInstructions"] = [
            "Preserve unrelated behavior.",
            "Preserve unrelated behavior!",
            "Verify the failure path and corrected path.",
        ]
        instruction = next(section for section in source["sections"] if section["id"] == "instructions")
        instruction["content"].extend([instruction["content"][0], instruction["content"][0]])

        result = PromptOptimizer().optimize(source, "bug fix")
        optimized_instructions = _content(result, "instructions")

        self.assertEqual(sum("preserve unrelated behavior" in item.casefold() for item in optimized_instructions), 1)
        self.assertGreaterEqual(result["diagnostics"]["instructionsMerged"], 3)

    def test_low_value_context_moves_to_appendix_without_being_lost(self) -> None:
        source = _execution_prompt()
        result = PromptOptimizer().optimize(source, "implementation")

        self.assertEqual([section["id"] for section in result["appendix"]], ["business_objective"])
        self.assertIn("## Appendix", result["prompt"])
        self.assertIn("Reduce outage investigation time", result["prompt"])
        self.assertEqual(result["diagnostics"]["movedToAppendix"][0]["sectionId"], "business_objective")

    def test_acceptance_repository_and_implementation_content_are_preserved_exactly(self) -> None:
        source = _execution_prompt()
        result = PromptOptimizer().optimize(source, "testing")

        for section_id in PROTECTED:
            original = next(section["content"] for section in source["sections"] if section["id"] == section_id)
            self.assertEqual(_content(result, section_id), original)
        self.assertTrue(result["diagnostics"]["acceptancePreserved"])
        self.assertTrue(result["diagnostics"]["repositoryEvidencePreserved"])
        self.assertTrue(result["diagnostics"]["implementationGuidancePreserved"])

    def test_quality_score_and_confidence_are_explainable(self) -> None:
        result = PromptOptimizer().optimize(_execution_prompt(), "implementation")

        self.assertEqual(result["promptQualityScore"], 100)
        self.assertEqual(result["promptConfidence"], 1.0)
        self.assertEqual(sum(result["diagnostics"]["qualityBreakdown"].values()), 100)
        self.assertAlmostEqual(sum(result["diagnostics"]["confidenceBreakdown"].values()), 1.0)

    def test_missing_repository_reduces_confidence_and_requires_review(self) -> None:
        code_indexed = PromptOptimizer().optimize(_execution_prompt(), "review")
        unavailable = PromptOptimizer().optimize(_execution_prompt("Unavailable"), "review")

        self.assertLess(unavailable["promptQualityScore"], code_indexed["promptQualityScore"])
        self.assertLess(unavailable["promptConfidence"], code_indexed["promptConfidence"])
        self.assertEqual(unavailable["status"], "NeedsReview")
        self.assertIn("Repository context is unavailable", " ".join(unavailable["warnings"]))

    def test_blocked_execution_prompt_remains_blocked(self) -> None:
        source = _execution_prompt(budget=16000, model="ollama")
        self.assertEqual(source["status"], "Blocked")

        result = PromptOptimizer().optimize(source, "implementation")

        self.assertEqual(result["status"], "Blocked")
        self.assertFalse(result["diagnostics"]["sourceReady"])
        self.assertTrue(result["diagnostics"]["contextLimitRespected"])

    def test_optimizer_is_deterministic_and_does_not_mutate_source(self) -> None:
        source = _execution_prompt()
        before = deepcopy(source)

        first = PromptOptimizer().optimize(source, "architecture")
        second = PromptOptimizer().optimize(source, "architecture")

        self.assertEqual(source, before)
        self.assertEqual(first["optimizedPromptId"], second["optimizedPromptId"])
        self.assertEqual(first["immutableHash"], second["immutableHash"])

    def test_optimizer_has_no_provider_or_network_dependency(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "prompt_optimizer"
        forbidden = (
            "provider_gateway", "phi_provider", "refinement.provider", "from openai", "import openai",
            "from anthropic", "import anthropic", "import requests", "import httpx", "urllib", "aiohttp",
        )
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8").casefold()
            for marker in forbidden:
                self.assertNotIn(marker.casefold(), source, f"{path.name} contains forbidden optimizer dependency {marker}")


if __name__ == "__main__":
    unittest.main()
