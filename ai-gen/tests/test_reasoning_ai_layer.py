from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.reasoning import (
    CallableReasoningProvider,
    ReasoningEngine,
    ReasoningProviderRegistry,
)
from backend.reasoning.services import PromptBuilder
from backend.reasoning.models import ReasoningRequest
from backend.reasoning.providers.phi_provider import PhiProvider


def engineering_context() -> dict:
    return {
        "contextId": "ctx-123",
        "contextVersion": "v3",
        "requirement": {
            "title": "Device Health Overview",
            "businessGoals": ["Identify unhealthy devices earlier."],
            "functionalRequirements": ["Show current device health."],
            "acceptanceCriteria": ["Operators can see offline devices."],
            "actors": ["Operations User"],
            "constraints": ["Use existing device services."],
        },
        "repository": {
            "mode": "CodeIndexed",
            "repositoryId": "repo-1",
            "repositorySnapshotVersion": "snapshot-7",
            "confidence": 90,
            "modules": ["Device Health"],
            "affectedModules": ["Device Health"],
            "services": ["DeviceHealthService"],
            "apiEndpoints": ["/api/devices/health"],
            "files": [
                {"path": "src/deviceHealth.ts", "confidence": 95},
                {"path": "tests/deviceHealth.test.ts", "confidence": 88},
            ],
            "warnings": [],
        },
        "azureDevOps": {
            "existingPlanning": [{"id": 245, "title": "Device health dashboard"}],
        },
        "engineeringMemory": {
            "matches": [{"id": "memory-1", "title": "Health status filtering"}],
        },
        "similarWork": {
            "matches": [{"id": "story-245", "confidence": 82}],
        },
        "architecture": {"layers": ["API", "Application"]},
        "dependencies": {"moduleDependencies": []},
        "impact": {
            "engineeringComplexity": "Medium",
            "potentialRisks": ["Stale telemetry may misstate health."],
        },
        "readiness": {"status": "ReadyWithRecommendations", "score": 78},
        "summary": {"readiness": "ReadyWithRecommendations", "repositoryConfidence": 90},
        "relevantDocumentation": [{"title": "Device Health Architecture"}],
        "rejectedContext": ["Firmware"],
    }


def valid_response() -> dict:
    return {
        "recommendation": {
            "title": "Extend Device Health",
            "action": "Reuse the existing device health service.",
        },
        "reasoning": ["The repository contains a relevant device health module."],
        "alternatives": [{"title": "Create new service", "reason": "Only if reuse is rejected."}],
        "evidence": [
            {"referenceId": "module:Device Health", "reason": "Matched affected module."},
            {"referenceId": "file:src/deviceHealth.ts", "reason": "Ranked repository file."},
        ],
        "risks": ["Telemetry freshness must be validated."],
        "tradeOffs": ["Reuse reduces scope but couples work to the existing service."],
        "impact": {"summary": "Changes the existing health workflow."},
        "confidence": 88,
    }


class ReasoningAILayerTests(unittest.TestCase):
    def test_deterministic_mode_works_without_provider(self) -> None:
        engine = ReasoningEngine(registry=ReasoningProviderRegistry())
        result = engine.reason("Planning Recommendation", engineering_context())

        self.assertEqual("Deterministic", result["reasoningMode"])
        self.assertEqual("Deterministic", result["provider"])
        self.assertTrue(result["recommendation"])
        self.assertTrue(result["reasoning"])
        self.assertTrue(result["alternatives"])
        self.assertTrue(result["evidence"])
        self.assertIn("confidence", result)

    def test_pluggable_provider_returns_explainable_result(self) -> None:
        provider = CallableReasoningProvider(
            "GPT",
            "gpt-test",
            lambda prompt, request, operation: {
                "content": valid_response(),
                "_reasoning_metadata": {
                    "promptTokens": 321,
                    "completionTokens": 123,
                    "latencyMs": 17,
                },
            },
        )
        engine = ReasoningEngine(registry=ReasoningProviderRegistry([provider]))
        result = engine.recommend(
            "Planning Recommendation",
            engineering_context(),
            provider="GPT",
            correlation_id="corr-1",
        )

        self.assertEqual("AI", result["reasoningMode"])
        self.assertEqual("GPT", result["provider"])
        self.assertEqual("gpt-test", result["model"])
        self.assertEqual(321, result["telemetry"]["promptTokens"])
        self.assertEqual("corr-1", result["diagnostics"]["correlationId"])
        self.assertTrue(result["promptVersion"].startswith("hei-reasoning-v1:"))
        self.assertEqual("Medium", result["confidence"]["level"])
        self.assertGreaterEqual(result["confidence"]["overall"], 55)

    def test_unknown_evidence_is_rejected_then_falls_back(self) -> None:
        response = valid_response()
        response["evidence"] = [{"referenceId": "file:invented/path.ts"}]
        calls = []

        def invoke(prompt, request, operation):
            calls.append(operation)
            return response

        provider = CallableReasoningProvider("GPT", "test", invoke)
        engine = ReasoningEngine(registry=ReasoningProviderRegistry([provider]))
        result = engine.reason("Execution Package", engineering_context(), provider="GPT")

        self.assertEqual(2, len(calls))
        self.assertEqual("Deterministic", result["reasoningMode"])
        self.assertNotIn("file:invented/path.ts", {
            item["referenceId"] for item in result["evidence"]
        })
        self.assertTrue(any("missing_valid_evidence" in item for item in result["warnings"]))

    def test_malformed_provider_output_retries_once(self) -> None:
        calls = []

        def invoke(prompt, request, operation):
            calls.append(prompt)
            return "not json"

        provider = CallableReasoningProvider("Claude", "test", invoke)
        engine = ReasoningEngine(registry=ReasoningProviderRegistry([provider]))
        result = engine.reason("Risk Analysis", engineering_context(), provider="Claude")

        self.assertEqual(2, len(calls))
        self.assertEqual(1, result["telemetry"]["retries"])
        self.assertEqual("Deterministic", result["reasoningMode"])
        self.assertTrue(any("parse_error" in item for item in result["warnings"]))

    def test_prompt_uses_context_evidence_and_budget_manager(self) -> None:
        context = engineering_context()
        context["requirement"]["requirementIntent"] = {
            "searchKeywords": ["device health"],
            "possibleModuleNames": ["Device Health"],
        }
        request = ReasoningRequest(
            workflowType="Architecture Review",
            engineeringContext=context,
        )
        built = PromptBuilder().build(request, provider="Phi", model="phi-test")

        self.assertIn("module:Device Health", built.prompt)
        self.assertIn("file:src/deviceHealth.ts", built.prompt)
        self.assertIn("requirementIntent", built.prompt)
        self.assertNotIn("Firmware", str(built.evidenceCatalog))
        self.assertLessEqual(
            built.diagnostics["finalPromptTokens"],
            built.diagnostics["contextLimit"],
        )
        self.assertIn("compressionApplied", built.diagnostics)

    def test_requirement_intent_prompt_uses_only_bounded_bootstrap_context(self) -> None:
        context = {
            "contextType": "RequirementIntentInput",
            "contextId": "requirement-intent-1",
            "contextVersion": "1.0",
            "requirement": {
                "title": "Device health",
                "normalizedRequirement": "Help operators identify unhealthy devices.",
                "sourceType": "PasteRequirement",
            },
            "metadata": {
                "projectId": "project-1",
                "repositoryId": "repository-1",
                "repositoryName": "LineDefender",
            },
        }
        built = PromptBuilder().build(
            ReasoningRequest(
                workflowType="Requirement Intent Analysis",
                engineeringContext=context,
                userRequirement="Help operators identify unhealthy devices.",
            ),
            provider="Phi",
            model="phi-test",
        )

        self.assertIn("requirementIntent", built.prompt)
        self.assertIn("source:requirement", built.prompt)
        self.assertNotIn("repository_evidence", built.prompt)
        self.assertNotIn("Engineering Memory", built.prompt)
        self.assertEqual(
            ["source:requirement"],
            [item["referenceId"] for item in built.evidenceCatalog],
        )

    def test_phi_refinement_uses_compact_prompt_and_budgeted_output(self) -> None:
        class Provider:
            def __init__(self) -> None:
                self.max_tokens = 0

            def is_enabled(self) -> bool:
                return True

            def probe_json(self, system_prompt, user_prompt, *, max_tokens):
                self.max_tokens = max_tokens
                return {
                    "parsed_json": {
                        "recommendation": {"refinement": {
                            "refinedRequirement": "Enable offline firmware updates for connected devices.",
                            "executiveSummary": "Support offline device firmware servicing.",
                            "businessGoal": "Maintain device operability where connectivity is unavailable.",
                            "problemStatement": "Firmware servicing currently depends on connectivity.",
                            "userIntent": "Update device firmware while offline.",
                            "primaryActor": "",
                            "coreCapabilities": ["Offline Firmware Update"],
                            "expectedOutcome": "Devices can receive firmware updates without connectivity.",
                            "businessEntities": ["Device", "Firmware"],
                            "engineeringConcepts": ["Offline Firmware Update"],
                            "domainTerminology": ["firmware"],
                            "repositorySearchHints": ["firmware update"],
                            "markdownSearchHints": ["firmware"],
                            "azureDevOpsSearchHints": ["offline firmware"],
                            "clarificationCandidates": ["Which device operator initiates the update?"],
                            "confidence": 80,
                        }},
                        "reasoning": ["The source explicitly requests offline firmware updates."],
                        "alternatives": [],
                        "evidence": [{"referenceId": "source:requirement"}],
                        "confidence": 80,
                    },
                    "prompt_tokens": 500,
                    "completion_tokens": 250,
                }

        context = {
            "contextType": "RequirementRefinementInput",
            "contextId": "requirement-refinement-1",
            "contextVersion": "1.0",
            "requirement": {
                "title": "Offline firmware updates",
                "normalizedRequirement": "Need offline firmware updates.",
                "sourceType": "PasteRequirement",
            },
            "metadata": {"projectId": "project-1", "projectName": "LineDefender"},
        }
        transport = Provider()
        provider = PhiProvider(transport, "Phi-4-mini-instruct")
        engine = ReasoningEngine(registry=ReasoningProviderRegistry([provider]))

        result = engine.refine(
            "Requirement Refinement", context,
            user_requirement="Need offline firmware updates.", provider="Phi",
        )

        self.assertEqual("AI", result["reasoningMode"])
        self.assertLessEqual(transport.max_tokens, 300)
        self.assertEqual(
            result["diagnostics"]["promptBudget"]["reservedOutputTokens"],
            transport.max_tokens,
        )
        self.assertLessEqual(
            result["diagnostics"]["promptBudget"]["finalPromptTokens"] + transport.max_tokens,
            result["diagnostics"]["promptBudget"]["contextLimit"],
        )

    def test_raw_sources_are_rejected(self) -> None:
        context = engineering_context()
        context["sourceCode"] = "secret source"
        engine = ReasoningEngine(registry=ReasoningProviderRegistry())

        with self.assertRaisesRegex(ValueError, "EngineeringContext only"):
            engine.reason("Code Review", context)

    def test_prompts_are_not_stored_without_explicit_logging(self) -> None:
        engine = ReasoningEngine(registry=ReasoningProviderRegistry())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HEI_REASONING_LOG_PROMPTS", None)
            result = engine.reason("Validation", engineering_context())

        records = engine.telemetry.list()
        self.assertFalse(result["telemetry"]["promptStored"])
        self.assertNotIn("prompt", records[0])

    def test_cache_reuses_same_context_and_prompt_version(self) -> None:
        calls = []

        def invoke(prompt, request, operation):
            calls.append(operation)
            return valid_response()

        engine = ReasoningEngine(
            registry=ReasoningProviderRegistry([
                CallableReasoningProvider("Local", "local-test", invoke)
            ])
        )
        first = engine.reason("Requirement Analysis", engineering_context(), provider="Local")
        second = engine.reason("Requirement Analysis", engineering_context(), provider="Local")

        self.assertEqual(1, len(calls))
        self.assertEqual(first["promptVersion"], second["promptVersion"])
        self.assertTrue(second["telemetry"]["cacheHit"])

    def test_transient_provider_fallback_is_not_cached(self) -> None:
        calls = []

        def invoke(prompt, request, operation):
            calls.append(operation)
            return "not json" if len(calls) <= 2 else valid_response()

        engine = ReasoningEngine(
            registry=ReasoningProviderRegistry([
                CallableReasoningProvider("Phi", "phi-test", invoke)
            ])
        )
        first = engine.reason("Requirement Analysis", engineering_context(), provider="Phi")
        second = engine.reason("Requirement Analysis", engineering_context(), provider="Phi")

        self.assertEqual("Deterministic", first["reasoningMode"])
        self.assertEqual("AI", second["reasoningMode"])
        self.assertEqual(3, len(calls))
        self.assertFalse(second["telemetry"].get("cacheHit", False))

    def test_reasoning_layer_has_no_fact_source_imports(self) -> None:
        root = Path(__file__).resolve().parents[1] / "backend" / "reasoning"
        content = "\n".join(
            path.read_text(encoding="utf-8")
            for path in root.rglob("*.py")
        )
        self.assertNotIn("backend.repository_intelligence", content)
        self.assertNotIn("backend.azure_devops", content)
        self.assertNotIn("backend.engineering_memory", content)
        self.assertNotIn("backend.project_intelligence", content)


if __name__ == "__main__":
    unittest.main()
