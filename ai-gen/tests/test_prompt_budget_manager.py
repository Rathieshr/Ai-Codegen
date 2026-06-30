from __future__ import annotations

import unittest
from pathlib import Path

from backend.prompt_budget import (
    PromptBudgetProfile,
    PromptSection,
    assemblePrompt,
    budgetProfileForProvider,
    buildPrompt,
    estimateTokens,
    probe_json_with_budget,
    providerCapabilities,
    validateBudget,
)


def section(
    section_id: str,
    source: str,
    content: object,
    *,
    priority: int = 50,
    required: bool = False,
    compressible: bool = True,
) -> PromptSection:
    return PromptSection(
        id=section_id,
        name=section_id.replace("_", " ").title(),
        priority=priority,
        estimatedTokens=estimateTokens(str(content)),
        required=required,
        compressible=compressible,
        source=source,
        content=content,
    )


class PromptBudgetManagerTests(unittest.TestCase):
    def test_phi_profile_uses_1200_tokens(self) -> None:
        profile = budgetProfileForProvider("azure_phi", "Phi-4")
        self.assertEqual(profile.context_limit, 1200)
        self.assertEqual(profile.capabilities.context_limit, 1200)

    def test_gpt5_profile_uses_32000_tokens(self) -> None:
        profile = budgetProfileForProvider("gpt-5", "gpt-5")
        self.assertEqual(profile.context_limit, 32000)
        self.assertTrue(profile.capabilities.supports_json_mode)

    def test_provider_capabilities_drive_budget_profile(self) -> None:
        capabilities = providerCapabilities("ollama", "llama3")
        profile = budgetProfileForProvider(capabilities.provider, capabilities.model)
        self.assertEqual(profile.provider, "ollama")
        self.assertEqual(profile.context_limit, 8000)

    def test_phi_small_model_removes_examples_and_diagnostics(self) -> None:
        profile = budgetProfileForProvider("azure_phi", "Phi-4")
        sections = self._base_sections(
            extra=[
                section("examples", "examples", "Example. " * 20, priority=40),
                section("diagnostics", "diagnostics", "Diagnostic. " * 20, priority=20),
            ]
        )
        result = buildPrompt(sections, profile)
        removed = set(result["diagnostics"]["removed_sections"])
        self.assertIn("examples", removed)
        self.assertIn("diagnostics", removed)

    def test_gpt_profile_keeps_richer_optional_context(self) -> None:
        profile = budgetProfileForProvider("gpt-5", "gpt-5")
        sections = self._base_sections(extra=[section("examples", "examples", "Example. " * 20, priority=40)])
        result = buildPrompt(sections, profile)
        self.assertIn("examples", {item["id"] for item in result["diagnostics"]["prompt_sections"]})
        self.assertFalse(result["diagnostics"]["compression_applied"])

    def test_prompt_order_is_preserved(self) -> None:
        sections = [
            section("instructions", "instructions", "Return JSON only.", priority=100, required=True, compressible=False),
            section("validation", "validation", {"status": "pending"}, priority=85, required=True, compressible=False),
            section("current_intent", "intent", {"goal": "Fault monitoring"}, priority=100, required=True, compressible=False),
            section("knowledge_summary", "knowledge", {"modules": ["Fault Monitoring"]}, priority=60),
        ]
        prompt = assemblePrompt(sections)
        self.assertLess(prompt.index("current_intent"), prompt.index("validation"))
        self.assertLess(prompt.index("validation"), prompt.index("knowledge_summary"))
        self.assertLess(prompt.index("knowledge_summary"), prompt.index("instructions"))

    def test_draft_is_compressed_when_prompt_exceeds_limit(self) -> None:
        profile = PromptBudgetProfile(provider="azure_phi", context_limit=260, reserved_tokens=40, section_budgets={"draft": 35})
        sections = self._base_sections(
            draft={"description": "Previous draft details. " * 120, "acceptance_criteria": ["AC " * 40] * 8}
        )
        result = buildPrompt(sections, profile)
        self.assertLess(result["diagnostics"]["section_tokens"]["previous_draft_summary"], 80)
        self.assertIn("previous_draft_summary", {step["section"] for step in result["diagnostics"]["compression_steps"] if step["action"] == "compress"})

    def test_knowledge_is_compressed(self) -> None:
        profile = PromptBudgetProfile(provider="azure_phi", context_limit=300, reserved_tokens=40, section_budgets={"knowledge_summary": 45})
        sections = self._base_sections(
            knowledge={"architecture_summary": "Architecture detail. " * 120, "modules": [f"Module {index}" for index in range(30)]}
        )
        result = buildPrompt(sections, profile)
        self.assertLessEqual(result["diagnostics"]["section_tokens"].get("knowledge_summary", 0), 80)
        self.assertIn("knowledge_summary", {step["section"] for step in result["diagnostics"]["compression_steps"]})

    def test_repository_is_compressed(self) -> None:
        profile = PromptBudgetProfile(provider="azure_phi", context_limit=300, reserved_tokens=40, section_budgets={"repository_evidence": 45})
        sections = self._base_sections(
            repository={"files": [f"src/module/file_{index}.cs" for index in range(80)], "evidence": ["Important evidence. " * 20] * 10}
        )
        result = buildPrompt(sections, profile)
        self.assertLessEqual(result["diagnostics"]["section_tokens"].get("repository_evidence", 0), 90)
        self.assertIn("repository_evidence", {step["section"] for step in result["diagnostics"]["compression_steps"]})

    def test_examples_and_diagnostics_are_removed_before_required_sections(self) -> None:
        profile = PromptBudgetProfile(provider="azure_phi", context_limit=180, reserved_tokens=40)
        sections = self._base_sections(
            extra=[
                section("examples", "examples", "Example output. " * 160, priority=40),
                section("diagnostics", "diagnostics", "Debug data. " * 160, priority=20),
            ]
        )
        result = buildPrompt(sections, profile)
        removed = set(result["diagnostics"]["removed_sections"])
        self.assertIn("examples", removed)
        self.assertIn("diagnostics", removed)
        self.assertIn("current_intent", result["diagnostics"]["section_tokens"])
        self.assertIn("instructions", result["diagnostics"]["section_tokens"])

    def test_required_sections_are_never_removed(self) -> None:
        profile = PromptBudgetProfile(provider="azure_phi", context_limit=120, reserved_tokens=40)
        sections = self._base_sections()
        result = buildPrompt(sections, profile)
        section_ids = {item["id"] for item in result["diagnostics"]["prompt_sections"]}
        self.assertIn("current_intent", section_ids)
        self.assertIn("dna", section_ids)
        self.assertIn("planning_boundary", section_ids)
        self.assertIn("validation", section_ids)
        self.assertIn("instructions", section_ids)

    def test_provider_call_is_blocked_when_required_sections_exceed_budget(self) -> None:
        class FakeProvider:
            def __init__(self) -> None:
                self.calls = 0

            def probe_json(self, **kwargs):
                self.calls += 1
                return {"parsed_json": {"ok": True}, "http_status": 200}

            def safe_config(self) -> dict:
                return {"provider": "azure_phi", "deployment": "Phi-4", "max_prompt_chars": 480}

        provider = FakeProvider()
        profile = PromptBudgetProfile(provider="azure_phi", context_limit=120, reserved_tokens=40)
        sections = [
            section("role", "role", "Role", priority=100, required=True, compressible=False),
            section("objective", "objective", "Objective " * 400, priority=100, required=True, compressible=False),
            section("current_work_item", "work_item", {"title": "Fault"}, priority=100, required=True, compressible=False),
            section("instructions", "instructions", "Return JSON only.", priority=100, required=True, compressible=False),
            section("output_schema", "schema", {"ok": True}, priority=100, required=True, compressible=False),
        ]
        built = buildPrompt(sections, profile)
        self.assertTrue(built["diagnostics"]["blocked"])
        result = probe_json_with_budget(provider, sections, operation="required_overflow")
        self.assertEqual(result["failure_reason"], "required_sections_exceed_budget")
        self.assertEqual(provider.calls, 0)

    def test_generation_modules_do_not_call_provider_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        files = [
            root / "backend/project_intelligence.py",
            root / "backend/refinement/task_refiner.py",
            root / "backend/story_planner/service.py",
            root / "backend/assistants/ba_assistant.py",
        ]
        combined = "\n".join(path.read_text() for path in files)
        self.assertNotIn("provider.probe_json(", combined)
        self.assertNotIn("provider.refine_json(", combined)

    def test_prompt_fits_provider_limit_after_optimization(self) -> None:
        profile = PromptBudgetProfile(provider="azure_phi", context_limit=420, reserved_tokens=40, section_budgets={"draft": 45, "knowledge_summary": 45, "repository_evidence": 45})
        sections = self._base_sections(
            draft={"description": "Draft. " * 200},
            knowledge={"architecture_summary": "Knowledge. " * 200, "modules": [f"Module {index}" for index in range(30)]},
            repository={"files": [f"src/file_{index}.cs" for index in range(80)]},
            extra=[section("examples", "examples", "Example. " * 120), section("diagnostics", "diagnostics", "Diagnostics. " * 120)],
        )
        result = buildPrompt(sections, profile)
        self.assertTrue(validateBudget(result["sections"], profile)["fits"])

    def _base_sections(
        self,
        *,
        draft: object | None = None,
        knowledge: object | None = None,
        repository: object | None = None,
        extra: list[PromptSection] | None = None,
    ) -> list[PromptSection]:
        sections = [
            section("current_intent", "intent", {"goal": "Review fault event"}, priority=100, required=True, compressible=False),
            section("current_capability", "capability", {"capability": "Fault Event Review"}, priority=100, required=True, compressible=False),
            section("dna", "dna", {"capability": "Fault Event Review"}, priority=95, required=True, compressible=False),
            section("planning_boundary", "planning_boundary", {"scope": "event review"}, priority=90, required=True, compressible=False),
            section("validation", "validation", {"status": "pending"}, priority=85, required=True, compressible=False),
            section("repository_evidence", "repository", repository or {"files": ["src/FaultEvent.cs"]}, priority=80),
            section("knowledge_summary", "knowledge", knowledge or {"modules": ["Fault Monitoring"], "flows": ["Fault Event Review"]}, priority=60),
            section("instructions", "instructions", "Return JSON only.", priority=100, required=True, compressible=False),
            section("previous_draft_summary", "draft", draft or {"description": "Draft summary"}, priority=50),
        ]
        if extra:
            sections.extend(extra)
        return sections


if __name__ == "__main__":
    unittest.main()
