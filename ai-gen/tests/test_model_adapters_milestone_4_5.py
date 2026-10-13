from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from backend.model_adapters import ModelAdapterCompiler
from backend.prompt_compiler import PromptCompiler
from backend.token_intelligence import TokenBudgetEngine
from tests.test_prompt_compiler_milestone_4_2 import _manifest


EXPECTED_ADAPTERS = ["gpt", "codex", "claude", "gemini", "glm", "qwen", "ollama"]


def _budgeted(budget: int = 2048) -> dict:
    compiled = PromptCompiler().compile(_manifest())
    return TokenBudgetEngine().optimize(compiled, budget_tokens=budget)


class ModelAdaptersMilestone45Tests(unittest.TestCase):
    def test_every_requested_adapter_produces_execution_prompt_version_and_diagnostics(self) -> None:
        compiler = ModelAdapterCompiler()
        self.assertEqual(compiler.supported_models(), EXPECTED_ADAPTERS)

        for model_id in EXPECTED_ADAPTERS:
            result = compiler.compile(_budgeted(), model_id)
            self.assertEqual(result["modelId"], model_id)
            self.assertEqual(result["status"], "Ready")
            self.assertEqual(result["promptVersion"], f"{model_id}-1.0")
            self.assertTrue(result["executionPromptId"].startswith(f"executionprompt_{model_id}_"))
            self.assertIn("# Execution Prompt", result["prompt"])
            self.assertIn("Authorized users can view severity", result["prompt"])
            self.assertGreater(result["estimatedTokens"], 0)
            self.assertTrue(result["diagnostics"]["modelAdaptationApplied"])
            self.assertFalse(result["diagnostics"]["providerInvoked"])
            self.assertEqual(result["diagnostics"]["networkCalls"], 0)
            self.assertFalse(result["diagnostics"]["llmUsed"])

    def test_adapters_reorder_sections_deterministically(self) -> None:
        compiler = ModelAdapterCompiler()
        expected = {
            "gpt": ["business_objective", "implementation_guidance", "repository_context", "validation", "constraints", "qa", "instructions"],
            "codex": ["instructions", "implementation_guidance", "repository_context", "validation", "qa", "constraints", "business_objective"],
            "claude": ["business_objective", "constraints", "repository_context", "implementation_guidance", "validation", "qa", "instructions"],
            "gemini": ["business_objective", "repository_context", "implementation_guidance", "constraints", "validation", "qa", "instructions"],
            "glm": ["instructions", "business_objective", "implementation_guidance", "validation", "repository_context", "constraints", "qa"],
            "qwen": ["implementation_guidance", "repository_context", "business_objective", "validation", "qa", "constraints", "instructions"],
            "ollama": ["business_objective", "implementation_guidance", "validation", "repository_context", "constraints", "qa", "instructions"],
        }
        budgeted = _budgeted()

        for model_id, order in expected.items():
            first = compiler.compile(budgeted, model_id)
            second = compiler.compile(budgeted, model_id)
            self.assertEqual(first["diagnostics"]["sectionOrder"], order)
            self.assertEqual(first["executionPromptId"], second["executionPromptId"])
            self.assertEqual(first["immutableHash"], second["immutableHash"])

    def test_wording_is_model_specific_without_changing_section_content(self) -> None:
        compiler = ModelAdapterCompiler()
        budgeted = _budgeted()
        original = {section["id"]: section["content"] for section in budgeted["sections"]}

        codex = compiler.compile(budgeted, "codex")
        claude = compiler.compile(budgeted, "claude")

        self.assertIn("minimal, test-backed edits", codex["prompt"])
        self.assertIn("Analyze the approved boundaries", claude["prompt"])
        self.assertNotEqual(codex["prompt"], claude["prompt"])
        for result in (codex, claude):
            for section in result["sections"]:
                self.assertEqual(section["content"], original[section["id"]])

    def test_model_capabilities_control_system_and_tool_instructions(self) -> None:
        compiler = ModelAdapterCompiler()
        gpt = compiler.compile(_budgeted(), "gpt")
        ollama = compiler.compile(_budgeted(), "ollama")

        self.assertTrue(gpt["systemPrompt"])
        self.assertTrue(gpt["diagnostics"]["capabilities"]["tools"])
        self.assertIn("Use repository tools", gpt["prompt"])
        self.assertFalse(ollama["diagnostics"]["capabilities"]["tools"])
        self.assertNotIn("Use repository tools", ollama["prompt"])
        self.assertIn("structured JSON output is not required", ollama["prompt"])

    def test_adapter_blocks_budget_larger_than_model_context(self) -> None:
        result = ModelAdapterCompiler().compile(_budgeted(16000), "ollama")

        self.assertEqual(result["status"], "Blocked")
        self.assertFalse(result["diagnostics"]["contextLimitRespected"])
        self.assertIn("exceeds this model profile's context window", " ".join(result["warnings"]))

    def test_adapter_does_not_mutate_budgeted_prompt(self) -> None:
        compiler = ModelAdapterCompiler()
        budgeted = _budgeted()
        before = deepcopy(budgeted)

        compiler.compile(budgeted, "gemini")

        self.assertEqual(budgeted, before)

    def test_missing_profile_or_adapter_fails_visibly(self) -> None:
        compiler = ModelAdapterCompiler()
        with self.assertRaisesRegex(ValueError, "Unknown model profile"):
            compiler.compile(_budgeted(), "missing")
        with self.assertRaisesRegex(ValueError, "No Model Adapter"):
            compiler.compile(_budgeted(), "deepseek")
        with self.assertRaisesRegex(ValueError, "No Model Adapter"):
            compiler.compile(_budgeted(), "phi")

    def test_model_adapters_have_no_provider_client_or_network_dependency(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "model_adapters"
        forbidden = (
            "provider_gateway", "phi_provider", "refinement.provider", "from openai", "import openai",
            "from anthropic", "import anthropic", "import requests", "import httpx", "urllib", "aiohttp",
        )
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8").casefold()
            for marker in forbidden:
                self.assertNotIn(marker.casefold(), source, f"{path.name} contains forbidden adapter dependency {marker}")


if __name__ == "__main__":
    unittest.main()
