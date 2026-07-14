from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.model_registry import MODEL_REGISTRY_VERSION, ModelRegistry, build_model_registry_router


EXPECTED_IDS = ["gpt", "codex", "claude", "gemini", "glm", "qwen", "ollama", "deepseek", "phi"]
REQUIRED_FIELDS = {
    "id", "name", "provider", "contextWindow", "reasoning", "maxOutput",
    "toolSupport", "vision", "streaming", "temperatureSupport", "jsonSupport",
    "systemPromptSupport", "capabilityTags", "enabled", "registryVersion",
}


class ModelRegistryMilestone44Tests(unittest.TestCase):
    def test_registry_contains_every_supported_model_in_deterministic_order(self) -> None:
        profiles = ModelRegistry().list()

        self.assertEqual([profile["id"] for profile in profiles], EXPECTED_IDS)
        self.assertEqual(len(profiles), len(EXPECTED_IDS))
        self.assertTrue(all(set(profile) == REQUIRED_FIELDS for profile in profiles))

    def test_profiles_expose_complete_capabilities_and_valid_limits(self) -> None:
        for profile in ModelRegistry().list():
            self.assertTrue(profile["provider"])
            self.assertGreater(profile["contextWindow"], 0)
            self.assertGreater(profile["maxOutput"], 0)
            self.assertLessEqual(profile["maxOutput"], profile["contextWindow"])
            self.assertTrue(profile["capabilityTags"])
            self.assertEqual(profile["registryVersion"], MODEL_REGISTRY_VERSION)
            for field in ("reasoning", "toolSupport", "vision", "streaming", "temperatureSupport", "jsonSupport", "systemPromptSupport", "enabled"):
                self.assertIsInstance(profile[field], bool)

    def test_lookup_is_case_insensitive_and_returns_defensive_copy(self) -> None:
        registry = ModelRegistry()
        first = registry.get("PHI")
        self.assertIsNotNone(first)
        first["capabilityTags"].append("mutated")

        second = registry.get("phi")
        self.assertNotIn("mutated", second["capabilityTags"])
        self.assertIsNone(registry.get("missing"))

    def test_duplicate_and_invalid_profiles_are_rejected(self) -> None:
        profile = ModelRegistry().get("gpt")
        with self.assertRaisesRegex(ValueError, "Duplicate model profile"):
            ModelRegistry([profile, profile])

        invalid = dict(profile)
        invalid["maxOutput"] = invalid["contextWindow"] + 1
        with self.assertRaisesRegex(ValueError, "maxOutput"):
            ModelRegistry([invalid])

    def test_api_lists_models_and_loads_one_profile(self) -> None:
        router = build_model_registry_router(ModelRegistry())
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}

        self.assertEqual(set(routes), {("GET", "/models"), ("GET", "/models/{model_id}")})
        listed = routes[("GET", "/models")]()
        self.assertEqual(listed["count"], 9)
        self.assertEqual([profile["id"] for profile in listed["models"]], EXPECTED_IDS)
        self.assertEqual(routes[("GET", "/models/{model_id}")]("codex")["provider"], "OpenAI")
        with self.assertRaises(HTTPException) as error:
            routes[("GET", "/models/{model_id}")]("unknown")
        self.assertEqual(error.exception.status_code, 404)

    def test_registry_has_no_adapter_provider_runtime_or_environment_dependency(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "model_registry"
        forbidden = (
            "prompt_budget", "provider_gateway", "phi_provider", "refinement.provider",
            "from openai", "import openai", "from anthropic", "import anthropic",
            "import requests", "import httpx", "os.getenv", "os.environ",
        )
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8").casefold()
            for marker in forbidden:
                self.assertNotIn(marker.casefold(), source, f"{path.name} contains forbidden registry dependency {marker}")


if __name__ == "__main__":
    unittest.main()
