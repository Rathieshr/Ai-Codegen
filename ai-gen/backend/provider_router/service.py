"""Persistence and platform events for provider routing decisions."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore

from .router import ProviderRouter


class ProviderRouterService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        router: ProviderRouter,
        prompt_cache: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.router = router
        self.prompt_cache = prompt_cache
        self.platform = platform

    def route(
        self,
        execution_manifest: dict[str, Any],
        *,
        execution_mode: str,
        repository_mode: str,
        target_task: Any,
        user_preference: Any,
        available_models: list[Any] | None,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        self._event("ProviderRoutingRequested", correlation_id, {"manifestId": execution_manifest.get("manifestId")})
        cache_context = self.router.cache_lookup_context(
            execution_manifest,
            execution_mode=execution_mode,
            repository_mode=repository_mode,
            target_task=target_task,
            user_preference=user_preference,
            available_models=available_models,
        )
        cache_model = cache_context["firstEligibleModel"]
        if self.prompt_cache and cache_model:
            cached = self.prompt_cache.lookup(
                execution_manifest,
                model_id=cache_model,
                execution_mode=cache_context["executionMode"],
                routing_target=cache_context["target"],
                correlation_id=correlation_id,
            )
            if cached:
                result = deepcopy(cached["routingResult"])
                result["cache"] = _cache_metadata(cached, "Hit")
                self._event("ProviderRoutingReused", correlation_id, {
                    "routingId": result.get("routingId"),
                    "cacheKey": cached.get("cacheKey"),
                    "modelId": cache_model,
                })
                return result
        result = self.router.route(
            execution_manifest,
            execution_mode=execution_mode,
            repository_mode=repository_mode,
            target_task=target_task,
            user_preference=user_preference,
            available_models=available_models,
        )
        values = self.store.read()
        existing = values.get(result["routingId"])
        if existing:
            if existing.get("immutableHash") != result.get("immutableHash"):
                raise ValueError("Provider routing identity collision detected.")
            result = deepcopy(existing)
        else:
            result["diagnostics"]["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
            values[result["routingId"]] = result
            self.store.write(values)
        cache_entry = None
        if self.prompt_cache:
            cache_entry = self.prompt_cache.put(
                execution_manifest,
                result,
                generation_duration_ms=(time.perf_counter() - started) * 1000,
                correlation_id=correlation_id,
            )
        self._event("ProviderRoutingCompleted", correlation_id, {
            "routingId": result["routingId"],
            "manifestId": result["executionManifestId"],
            "modelId": result["selectedProvider"]["modelId"],
            "target": result["routingDecision"]["target"],
        })
        response = deepcopy(result)
        if cache_entry:
            response["cache"] = _cache_metadata(cache_entry, "Miss")
        return response

    def get(self, routing_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(routing_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def diagnostics(self, routing_id: str) -> dict[str, Any] | None:
        value = self.get(routing_id)
        if not value:
            return None
        return {
            "routingId": routing_id,
            "executionManifestId": value["executionManifestId"],
            "selectedProvider": value["selectedProvider"],
            "routingDecision": value["routingDecision"],
            "reasons": value["reasons"],
            "warnings": value["warnings"],
            **value["diagnostics"],
        }

    def _event(self, event_type: str, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "API", "correlationId": correlation_id, "payload": payload})


def _cache_metadata(entry: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "status": status,
        "cacheKey": entry.get("cacheKey"),
        "hitCount": int(entry.get("hitCount") or 0),
        "estimatedTokensSaved": int(entry.get("estimatedTokens") or 0) if status == "Hit" else 0,
        "estimatedGenerationMsSaved": float(entry.get("generationDurationMs") or 0) if status == "Hit" else 0.0,
    }
