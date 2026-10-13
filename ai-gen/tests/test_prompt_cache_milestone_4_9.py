from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fastapi import HTTPException

from backend.execution_manifest import ExecutionManifestBuilder
from backend.model_registry import ModelRegistry
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore
from backend.prompt_cache import PromptCacheService, build_cache_key, build_prompt_cache_router
from backend.provider_router import ProviderRouter, ProviderRouterService
from backend.token_intelligence.models import stable_hash
from tests.test_execution_manifest_milestone_4_1 import _package


def _manifest() -> dict:
    return ExecutionManifestBuilder().build(_package())


def _changed(manifest: dict, field: str, value: str) -> dict:
    changed = deepcopy(manifest)
    if field == "sourcePackageId":
        changed[field] = value
    elif field == "manifestVersion":
        changed[field] = value
    else:
        changed["sourceVersions"][field] = value
    changed["immutableHash"] = stable_hash({
        "manifestVersion": changed["manifestVersion"],
        "sourcePackageId": changed["sourcePackageId"],
        "sourceVersions": changed["sourceVersions"],
        "priorIdentity": manifest["immutableHash"],
    })
    changed["manifestId"] = f"execmanifest_{changed['immutableHash'][:12]}"
    return changed


class CountingProviderRouter(ProviderRouter):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.route_calls = 0

    def route(self, *args, **kwargs):
        self.route_calls += 1
        return super().route(*args, **kwargs)


class PromptCacheMilestone49Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.platform = PlatformFoundation(self.root / "platform")
        self.cache = PromptCacheService(
            JsonMapStore(self.root / "prompt-cache.json"),
            JsonMapStore(self.root / "prompt-cache-metrics.json"),
            platform=self.platform,
        )
        self.router = CountingProviderRouter(model_registry=ModelRegistry())
        self.service = ProviderRouterService(
            JsonMapStore(self.root / "provider-routes.json"),
            router=self.router,
            prompt_cache=self.cache,
            platform=self.platform,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _route(self, manifest: dict | None = None, **overrides) -> dict:
        values = {
            "execution_mode": "Implementation",
            "repository_mode": "CodeIndexed",
            "target_task": {"type": "Coding"},
            "user_preference": "",
            "available_models": None,
        }
        values.update(overrides)
        return self.service.route(manifest or _manifest(), **values)

    def test_cache_key_contains_complete_prompt_lineage(self) -> None:
        manifest = _manifest()
        cache_key, key = build_cache_key(
            manifest,
            model_id="codex",
            execution_mode="implementation",
            routing_target="coding",
        )

        self.assertTrue(cache_key.startswith("promptcache_"))
        self.assertEqual(key["executionManifestVersion"], "1.0")
        self.assertEqual(key["executionManifestIdentity"], manifest["immutableHash"])
        self.assertEqual(key["executionPackageId"], manifest["sourcePackageId"])
        self.assertEqual(key["executionPackageVersion"], "2.0")
        self.assertEqual(key["repositorySnapshotVersion"], "snapshot-v7")
        self.assertEqual(key["knowledgeVersion"], "knowledge-v5")
        self.assertEqual(key["memoryVersion"], "memory-v1")
        self.assertEqual(key["modelId"], "codex")
        self.assertEqual(key["executionMode"], "implementation")

    def test_second_identical_route_is_cache_hit_without_prompt_regeneration(self) -> None:
        first = self._route()
        second = self._route()

        self.assertEqual(first["cache"]["status"], "Miss")
        self.assertEqual(second["cache"]["status"], "Hit")
        self.assertEqual(first["routingId"], second["routingId"])
        self.assertEqual(self.router.route_calls, 1)
        self.assertGreater(second["cache"]["estimatedTokensSaved"], 0)
        metrics = self.cache.metrics()
        self.assertEqual(metrics["requests"], 2)
        self.assertEqual(metrics["hits"], 1)
        self.assertEqual(metrics["misses"], 1)
        self.assertEqual(metrics["generationsAvoided"], 1)
        self.assertEqual(metrics["hitRate"], 50.0)

    def test_repository_knowledge_memory_and_package_changes_cause_misses(self) -> None:
        dimensions = (
            ("repositorySnapshotVersion", "snapshot-v8"),
            ("knowledgeVersion", "knowledge-v6"),
            ("engineeringMemoryVersion", "memory-v2"),
            ("executionPackageVersion", "2.1"),
            ("sourcePackageId", "execpkg_changed"),
        )
        for field, value in dimensions:
            with self.subTest(field=field):
                temp_root = self.root / field
                cache = PromptCacheService(
                    JsonMapStore(temp_root / "cache.json"),
                    JsonMapStore(temp_root / "metrics.json"),
                )
                router = CountingProviderRouter(model_registry=ModelRegistry())
                service = ProviderRouterService(
                    JsonMapStore(temp_root / "routes.json"),
                    router=router,
                    prompt_cache=cache,
                )
                original = _manifest()
                first = service.route(
                    original, execution_mode="Implementation", repository_mode="CodeIndexed",
                    target_task={"type": "Coding"}, user_preference="", available_models=None,
                )
                changed = _changed(original, field, value)
                second = service.route(
                    changed, execution_mode="Implementation", repository_mode="CodeIndexed",
                    target_task={"type": "Coding"}, user_preference="", available_models=None,
                )
                self.assertEqual(first["cache"]["status"], "Miss")
                self.assertEqual(second["cache"]["status"], "Miss")
                self.assertEqual(router.route_calls, 2)

    def test_model_and_execution_mode_changes_invalidate_prior_route(self) -> None:
        manifest = _manifest()
        codex = self._route(manifest)
        gpt = self._route(
            manifest,
            user_preference="gpt",
            available_models=["codex", "gpt"],
        )
        review = self._route(manifest, execution_mode="Review")

        self.assertEqual(codex["selectedProvider"]["modelId"], "codex")
        self.assertEqual(gpt["selectedProvider"]["modelId"], "gpt")
        self.assertEqual(gpt["cache"]["status"], "Miss")
        self.assertEqual(review["prompt"]["mode"], "review")
        self.assertEqual(review["cache"]["status"], "Miss")
        self.assertEqual(self.router.route_calls, 3)
        self.assertGreaterEqual(self.cache.metrics()["invalidations"], 2)

    def test_cache_persists_across_service_instances(self) -> None:
        first = self._route()
        second_cache = PromptCacheService(
            JsonMapStore(self.root / "prompt-cache.json"),
            JsonMapStore(self.root / "prompt-cache-metrics.json"),
        )
        second_router = CountingProviderRouter(model_registry=ModelRegistry())
        second_service = ProviderRouterService(
            JsonMapStore(self.root / "provider-routes.json"),
            router=second_router,
            prompt_cache=second_cache,
        )
        second = second_service.route(
            _manifest(), execution_mode="Implementation", repository_mode="CodeIndexed",
            target_task={"type": "Coding"}, user_preference="", available_models=None,
        )

        self.assertEqual(first["routingId"], second["routingId"])
        self.assertEqual(second["cache"]["status"], "Hit")
        self.assertEqual(second_router.route_calls, 0)

    def test_manual_invalidation_and_cache_apis(self) -> None:
        routed = self._route()
        cache_key = routed["cache"]["cacheKey"]
        router = build_prompt_cache_router(self.cache)
        routes = {(next(iter(route.methods)), route.path): route.endpoint for route in router.routes}

        self.assertEqual(set(routes), {
            ("GET", "/prompt-cache/metrics"),
            ("GET", "/prompt-cache/entries/{cache_key}"),
            ("POST", "/prompt-cache/invalidate"),
        })
        entry = routes[("GET", "/prompt-cache/entries/{cache_key}")](cache_key)
        result = routes[("POST", "/prompt-cache/invalidate")]({
            "criteria": {"modelId": "codex"},
            "reason": "Model configuration changed.",
        })
        self.assertEqual(entry["status"], "Active")
        self.assertEqual(result["invalidated"], 1)
        self.assertEqual(self.cache.get(cache_key)["status"], "Invalidated")
        self.assertEqual(routes[("GET", "/prompt-cache/metrics")]()["activeEntries"], 0)

        with self.assertRaises(HTTPException) as error:
            routes[("POST", "/prompt-cache/invalidate")]({})
        self.assertEqual(error.exception.status_code, 422)

    def test_prompt_cache_is_provider_free(self) -> None:
        root = Path(__file__).parents[1] / "backend" / "prompt_cache"
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
