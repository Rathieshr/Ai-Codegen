from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore
from backend.prompt_compiler import PromptCompiler, PromptCompilerService, build_prompt_compiler_router


def _manifest(repository_mode: str = "CodeIndexed", *, files: list | None = None) -> dict:
    relevant_files = files if files is not None else [
        {"path": "src/fault/FaultEventController.cs", "confidence": 0.92, "reason": "Handles fault details."}
    ]
    return {
        "manifestId": "execmanifest_compiler_fixture",
        "manifestVersion": "1.0",
        "sourcePackageId": "execpkg_compiler_fixture",
        "sourceVersions": {"repositorySnapshotVersion": "snapshot-v9"},
        "objective": "Implement critical fault event details.",
        "businessGoal": "Reduce outage investigation time.",
        "acceptanceCriteria": [
            {"acceptanceCriteriaId": "AC001", "acceptanceText": "Authorized users can view severity.", "implementationArea": "API", "validationExpectation": "Permission test."}
        ],
        "repositoryContext": {
            "repositoryMode": repository_mode,
            "snapshot": "snapshot-v9",
            "relevantFiles": relevant_files,
            "relevantModules": ["Fault Monitoring"],
            "relevantFlows": ["Fault Event Review Flow"],
            "relevantAPIs": ["GET /fault-events/{id}"],
            "relevantServices": ["Fault Event Service"],
        },
        "relevantFiles": relevant_files,
        "dependencies": ["Telemetry Service", "Telemetry Service"],
        "implementationGuidance": {
            "implementationObjective": "Implement critical fault event details.",
            "recommendedSequence": ["Inspect repository evidence.", "Implement the smallest change.", "Implement the smallest change."],
            "implementationBoundaries": ["Fault details only."],
            "blockedModules": ["Firmware Management", "Firmware Management"],
            "blockedFlows": ["Firmware Rollout Flow"],
        },
        "validationGuidance": {
            "acceptanceMapping": [],
            "architectureConstraints": ["Preserve API compatibility."],
            "permissionRequirements": ["Role-based access"],
            "regressionAreas": ["Fault Monitoring"],
        },
        "qaGuidance": {
            "suggestedTests": ["Fault details test", "Fault details test"],
            "negativeTests": ["Reject missing event."],
        },
        "engineeringStandards": ["Structured logging", "Structured logging", "Role-based access"],
        "risks": ["Telemetry may be stale.", "Telemetry may be stale."],
        "warnings": [],
        "confidence": 0.91,
        "tokenEstimates": {"manifestTokens": 800},
        "immutable": True,
        "immutableHash": "fixture-hash",
        "generatedAt": "2026-07-13T00:00:00+00:00",
        "diagnostics": {"llmUsed": False},
    }


def _section(compiled: dict, section_id: str) -> dict:
    return next(item for item in compiled["sections"] if item["id"] == section_id)


class PromptCompilerMilestone42Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.service = PromptCompilerService(JsonMapStore(self.root / "compiled.json"), platform=self.platform)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_small_manifest_compiles_in_required_deterministic_order(self) -> None:
        first = PromptCompiler().compile(_manifest())
        second = PromptCompiler().compile(_manifest())

        self.assertEqual(
            [item["id"] for item in first["sections"]],
            ["business_objective", "repository_context", "implementation_guidance", "validation", "qa", "constraints", "instructions"],
        )
        self.assertEqual(first["compiledPromptId"], second["compiledPromptId"])
        self.assertEqual(first["immutableHash"], second["immutableHash"])
        self.assertFalse(first["diagnostics"]["tokenOptimizationApplied"])
        self.assertFalse(first["diagnostics"]["modelAdaptationApplied"])
        self.assertFalse(first["diagnostics"]["providerSelected"])
        self.assertFalse(first["diagnostics"]["llmUsed"])

    def test_large_manifest_is_sectioned_without_truncation(self) -> None:
        manifest = _manifest()
        manifest["acceptanceCriteria"] = [
            {"acceptanceCriteriaId": f"AC{index:03d}", "acceptanceText": f"Criterion {index}", "implementationArea": "API", "validationExpectation": "Test"}
            for index in range(1, 401)
        ]

        compiled = PromptCompiler().compile(manifest)

        acceptance = _section(compiled, "validation")["content"]["acceptanceCriteria"]
        self.assertEqual(len(acceptance), 400)
        self.assertEqual(acceptance[-1]["acceptanceCriteriaId"], "AC400")

    def test_repeated_guidance_is_merged_without_reordering(self) -> None:
        compiled = PromptCompiler().compile(_manifest())
        implementation = _section(compiled, "implementation_guidance")["content"]
        constraints = _section(compiled, "constraints")["content"]

        self.assertEqual(implementation["recommendedSequence"].count("Implement the smallest change."), 1)
        self.assertEqual(constraints["dependencies"], ["Telemetry Service"])
        self.assertEqual(constraints["engineeringStandards"].count("Structured logging"), 1)
        self.assertEqual(constraints["risks"], ["Telemetry may be stale."])
        self.assertEqual(constraints["blockedModules"], ["Firmware Management"])
        self.assertGreater(compiled["diagnostics"]["duplicateValuesRemoved"], 0)

    def test_missing_repository_compiles_with_explicit_unavailable_state(self) -> None:
        manifest = _manifest()
        manifest["repositoryContext"] = {}
        manifest["relevantFiles"] = []

        compiled = PromptCompiler().compile(manifest)
        repository = _section(compiled, "repository_context")["content"]

        self.assertEqual(repository["repositoryMode"], "Unavailable")
        self.assertFalse(repository["evidenceAvailable"])
        self.assertEqual(repository["relevantFiles"], [])
        self.assertIn("Repository context is unavailable.", compiled["warnings"])

    def test_knowledge_snapshot_keeps_modules_but_removes_code_evidence(self) -> None:
        compiled = PromptCompiler().compile(_manifest("Knowledge Snapshot"))
        repository = _section(compiled, "repository_context")["content"]

        self.assertEqual(repository["repositoryMode"], "KnowledgeSnapshot")
        self.assertEqual(repository["relevantFiles"], [])
        self.assertEqual(repository["relevantAPIs"], [])
        self.assertEqual(repository["relevantServices"], [])
        self.assertEqual(repository["relevantModules"], ["Fault Monitoring"])
        self.assertFalse(repository["evidenceAvailable"])

    def test_repository_unavailable_removes_all_repository_evidence(self) -> None:
        compiled = PromptCompiler().compile(_manifest("Unavailable"))
        repository = _section(compiled, "repository_context")["content"]

        self.assertEqual(repository["repositoryMode"], "Unavailable")
        for field in ("relevantFiles", "relevantAPIs", "relevantServices", "relevantModules", "relevantFlows"):
            self.assertEqual(repository[field], [])

    def test_service_persists_compiled_prompt_and_api_loads_by_manifest_id(self) -> None:
        manifest = _manifest()

        class ManifestService:
            def get(self, manifest_id: str) -> dict | None:
                return manifest if manifest_id == manifest["manifestId"] else None

        router = build_prompt_compiler_router(self.service, ManifestService())
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {("POST", "/prompt-compiler/compile"), ("GET", "/prompt-compiler/{compiled_prompt_id}")})

        compiled = routes[("POST", "/prompt-compiler/compile")]({"executionManifestId": manifest["manifestId"], "correlationId": "corr-compiler"})
        loaded = routes[("GET", "/prompt-compiler/{compiled_prompt_id}")](compiled["compiledPromptId"])
        self.assertEqual(loaded["immutableHash"], compiled["immutableHash"])
        self.assertGreater(self.platform.events.list_recent(event_type="PromptCompilationCompleted")["count"], 0)

    def test_compiler_module_has_no_budget_provider_formatter_or_llm_imports(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "prompt_compiler"
        forbidden = ("prompt_budget", "prompt_builder", "refinement.provider", "phi_provider", "openai", "anthropic")
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8").casefold()
            for marker in forbidden:
                self.assertNotIn(marker.casefold(), source, f"{path.name} contains forbidden compiler dependency {marker}")


if __name__ == "__main__":
    unittest.main()
