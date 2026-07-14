from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.execution_manifest import ExecutionManifestBuilder
from backend.model_registry import ModelRegistry
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore
from backend.provider_router import ProviderRouter, ProviderRouterService, build_provider_router_api
from tests.test_execution_manifest_milestone_4_1 import _package


def _manifest() -> dict:
    return ExecutionManifestBuilder().build(_package())


class ProviderRouterMilestone48Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.router = ProviderRouter(model_registry=ModelRegistry())
        self.service = ProviderRouterService(
            JsonMapStore(self.root / "provider-routes.json"),
            router=self.router,
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _route(self, target: str, **overrides) -> dict:
        values = {
            "execution_mode": "Implementation",
            "repository_mode": "CodeIndexed",
            "target_task": {"type": target},
            "user_preference": "",
            "available_models": None,
        }
        values.update(overrides)
        return self.router.route(_manifest(), **values)

    def test_required_target_rules_select_expected_models(self) -> None:
        expected = {
            "Coding": "codex",
            "Architecture": "gpt",
            "UI": "gemini",
            "Documentation": "gpt",
            "Large Context": "claude",
            "Local": "ollama",
        }
        for target, model_id in expected.items():
            result = self._route(target)
            self.assertEqual(result["selectedProvider"]["modelId"], model_id, target)
            self.assertEqual(result["routingDecision"]["status"], "Selected")
            self.assertEqual(result["prompt"]["status"], "Ready")
            self.assertEqual(result["prompt"]["sourceExecutionManifestId"], result["executionManifestId"])

    def test_coding_falls_back_to_claude_when_codex_is_unavailable(self) -> None:
        result = self._route("Coding", available_models=["claude", "gpt"])

        self.assertEqual(result["selectedProvider"]["modelId"], "claude")
        self.assertTrue(result["routingDecision"]["fallbackUsed"])
        rejected = {item["modelId"]: item["reason"] for item in result["diagnostics"]["rejectedModels"]}
        self.assertIn("not in the available-model set", rejected["codex"])

    def test_valid_user_preference_overrides_default_after_eligibility_checks(self) -> None:
        result = self._route("Coding", user_preference="GPT", available_models=["codex", "gpt"])

        self.assertEqual(result["selectedProvider"]["modelId"], "gpt")
        self.assertTrue(result["routingDecision"]["userPreferenceApplied"])
        self.assertIn("User preference selected GPT", " ".join(result["reasons"]))

    def test_unavailable_preference_is_explained_and_rule_selection_continues(self) -> None:
        result = self._route("UI", user_preference="Claude Code", available_models=["gemini"])

        self.assertEqual(result["selectedProvider"]["modelId"], "gemini")
        self.assertFalse(result["routingDecision"]["userPreferenceApplied"])
        self.assertIn("was unavailable", " ".join(result["reasons"]))

    def test_models_without_adapters_are_rejected_and_empty_availability_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "No provider route is available"):
            self._route("Coding", available_models=["phi", "deepseek"])
        with self.assertRaisesRegex(ValueError, "No provider route is available"):
            self._route("Coding", available_models=[])

    def test_manifest_repository_mode_is_source_of_truth(self) -> None:
        result = self._route("Coding", repository_mode="Unavailable")

        self.assertEqual(result["routingDecision"]["repositoryMode"], "CodeIndexed")
        self.assertIn("source of truth", " ".join(result["warnings"]))
        self.assertEqual(result["diagnostics"]["manifestRepositoryMode"], "CodeIndexed")

    def test_target_language_and_execution_mode_are_detected(self) -> None:
        ui = self.router.route(
            _manifest(), execution_mode="Implementation", repository_mode="CodeIndexed",
            target_task="Build the React device health screen", user_preference="", available_models=None,
        )
        architecture = self.router.route(
            _manifest(), execution_mode="Architecture", repository_mode="CodeIndexed",
            target_task="Define service boundaries", user_preference="", available_models=None,
        )

        self.assertEqual(ui["routingDecision"]["target"], "ui")
        self.assertEqual(ui["selectedProvider"]["modelId"], "gemini")
        self.assertEqual(architecture["routingDecision"]["target"], "architecture")
        self.assertEqual(architecture["prompt"]["mode"], "architecture")

    def test_routing_is_immutable_persisted_and_provider_free(self) -> None:
        manifest = _manifest()
        first = self.service.route(
            manifest, execution_mode="Bug Fix", repository_mode="CodeIndexed",
            target_task={"type": "Coding"}, user_preference="", available_models=None,
        )
        second = self.service.route(
            manifest, execution_mode="Bug Fix", repository_mode="CodeIndexed",
            target_task={"type": "Coding"}, user_preference="", available_models=None,
        )

        self.assertEqual(first["routingId"], second["routingId"])
        self.assertEqual(first["immutableHash"], second["immutableHash"])
        self.assertFalse(first["diagnostics"]["providerInvoked"])
        self.assertEqual(first["diagnostics"]["networkCalls"], 0)
        self.assertFalse(first["diagnostics"]["llmUsed"])
        self.assertEqual(self.service.get(first["routingId"])["routingId"], first["routingId"])

    def test_api_resolves_manifest_and_exposes_decision_diagnostics(self) -> None:
        manifest = _manifest()

        class ManifestService:
            def get(self, manifest_id: str):
                return manifest if manifest_id == manifest["manifestId"] else None

        router = build_provider_router_api(self.service, ManifestService())
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}
        self.assertEqual(set(routes), {
            ("POST", "/provider-router/route"),
            ("GET", "/provider-router/decisions/{routing_id}"),
            ("GET", "/provider-router/decisions/{routing_id}/diagnostics"),
        })
        routed = routes[("POST", "/provider-router/route")]({
            "executionManifestId": manifest["manifestId"],
            "executionMode": "Documentation",
            "repositoryMode": "CodeIndexed",
            "targetTask": {"type": "Documentation"},
            "availableModels": ["gpt", "claude"],
        })
        loaded = routes[("GET", "/provider-router/decisions/{routing_id}")](routed["routingId"])
        diagnostics = routes[("GET", "/provider-router/decisions/{routing_id}/diagnostics")](routed["routingId"])
        self.assertEqual(loaded["selectedProvider"]["modelId"], "gpt")
        self.assertEqual(diagnostics["appliedRule"], "documentation")

        with self.assertRaises(HTTPException) as error:
            routes[("POST", "/provider-router/route")]({"executionManifestId": "missing"})
        self.assertEqual(error.exception.status_code, 404)

    def test_router_module_has_no_provider_client_or_network_dependency(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "provider_router"
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
