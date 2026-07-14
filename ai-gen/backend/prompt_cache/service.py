"""Persistent Prompt Cache with lineage-aware invalidation and savings metrics."""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.platform.shared import JsonMapStore

from .key import build_cache_key, invalidation_reasons, missing_lineage
from .models import PROMPT_CACHE_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptCacheService:
    def __init__(self, store: JsonMapStore, metrics_store: JsonMapStore, *, platform: Any | None = None) -> None:
        self.store = store
        self.metrics_store = metrics_store
        self.platform = platform
        self._lock = threading.RLock()

    def lookup(
        self,
        execution_manifest: dict[str, Any],
        *,
        model_id: str,
        execution_mode: str,
        routing_target: str,
        correlation_id: str = "",
    ) -> dict[str, Any] | None:
        cache_key, key = build_cache_key(
            execution_manifest,
            model_id=model_id,
            execution_mode=execution_mode,
            routing_target=routing_target,
        )
        with self._lock:
            values = self.store.read()
            invalidated = self._invalidate_related(values, key)
            entry = values.get(cache_key)
            if not isinstance(entry, dict) or entry.get("status") != "Active":
                self.store.write(values)
                self._record_metrics(requests=1, misses=1, invalidations=invalidated)
                self._event("PromptCacheMiss", correlation_id, {"cacheKey": cache_key, "modelId": model_id})
                return None
            entry["hitCount"] = int(entry.get("hitCount") or 0) + 1
            entry["lastAccessedAt"] = _now()
            values[cache_key] = entry
            self.store.write(values)
            saved_ms = float(entry.get("generationDurationMs") or 0)
            saved_tokens = int(entry.get("estimatedTokens") or 0)
            self._record_metrics(
                requests=1,
                hits=1,
                generationsAvoided=1,
                estimatedGenerationMsSaved=saved_ms,
                estimatedTokensSaved=saved_tokens,
            )
            self._event("PromptCacheHit", correlation_id, {
                "cacheKey": cache_key,
                "routingId": entry.get("routingId"),
                "modelId": model_id,
                "estimatedTokensSaved": saved_tokens,
            })
            return deepcopy(entry)

    def put(
        self,
        execution_manifest: dict[str, Any],
        routing_result: dict[str, Any],
        *,
        generation_duration_ms: float,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        decision = routing_result.get("routingDecision") if isinstance(routing_result.get("routingDecision"), dict) else {}
        provider = routing_result.get("selectedProvider") if isinstance(routing_result.get("selectedProvider"), dict) else {}
        prompt = routing_result.get("prompt") if isinstance(routing_result.get("prompt"), dict) else {}
        cache_key, key = build_cache_key(
            execution_manifest,
            model_id=str(provider.get("modelId") or ""),
            execution_mode=str(decision.get("executionMode") or ""),
            routing_target=str(decision.get("target") or ""),
        )
        now = _now()
        entry = {
            "cacheKey": cache_key,
            "cacheVersion": PROMPT_CACHE_VERSION,
            "key": key,
            "status": "Active",
            "routingId": str(routing_result.get("routingId") or ""),
            "routingResult": deepcopy(routing_result),
            "estimatedTokens": int(prompt.get("estimatedTokens") or 0),
            "generationDurationMs": round(float(generation_duration_ms), 2),
            "hitCount": 0,
            "createdAt": now,
            "lastAccessedAt": now,
            "invalidatedAt": "",
            "invalidationReasons": [],
            "diagnostics": {
                "missingLineage": missing_lineage(key),
                "providerInvoked": False,
                "networkCalls": 0,
            },
        }
        with self._lock:
            values = self.store.read()
            invalidated = self._invalidate_related(values, key)
            existing = values.get(cache_key)
            if isinstance(existing, dict) and existing.get("status") == "Active":
                return deepcopy(existing)
            values[cache_key] = entry
            self.store.write(values)
            self._record_metrics(writes=1, invalidations=invalidated)
        self._event("PromptCached", correlation_id, {
            "cacheKey": cache_key,
            "routingId": entry["routingId"],
            "modelId": key["modelId"],
        })
        return deepcopy(entry)

    def get(self, cache_key: str) -> dict[str, Any] | None:
        value = self.store.read().get(cache_key)
        return deepcopy(value) if isinstance(value, dict) else None

    def invalidate(self, criteria: dict[str, Any], *, reason: str = "Manual invalidation", correlation_id: str = "") -> dict[str, Any]:
        normalized = {str(key): str(value) for key, value in criteria.items() if value is not None}
        now = _now()
        invalidated: list[str] = []
        with self._lock:
            values = self.store.read()
            for cache_key, entry in values.items():
                if not isinstance(entry, dict) or entry.get("status") != "Active":
                    continue
                key = entry.get("key") if isinstance(entry.get("key"), dict) else {}
                if normalized and not all(str(key.get(field) or "") == value for field, value in normalized.items()):
                    continue
                entry["status"] = "Invalidated"
                entry["invalidatedAt"] = now
                entry["invalidationReasons"] = [reason]
                invalidated.append(cache_key)
            self.store.write(values)
            self._record_metrics(invalidations=len(invalidated))
        self._event("PromptCacheInvalidated", correlation_id, {"cacheKeys": invalidated, "reason": reason})
        return {"invalidated": len(invalidated), "cacheKeys": invalidated, "reason": reason}

    def metrics(self) -> dict[str, Any]:
        metrics = self._metrics()
        requests = int(metrics["requests"])
        hits = int(metrics["hits"])
        entries = [value for value in self.store.read().values() if isinstance(value, dict)]
        return {
            **metrics,
            "hitRate": round((hits / requests) * 100, 2) if requests else 0.0,
            "activeEntries": sum(1 for entry in entries if entry.get("status") == "Active"),
            "invalidatedEntries": sum(1 for entry in entries if entry.get("status") == "Invalidated"),
        }

    def _invalidate_related(self, values: dict[str, Any], current_key: dict[str, Any]) -> int:
        invalidated = 0
        now = _now()
        for entry in values.values():
            if not isinstance(entry, dict) or entry.get("status") != "Active":
                continue
            previous = entry.get("key") if isinstance(entry.get("key"), dict) else {}
            if previous.get("executionPackageId") != current_key.get("executionPackageId"):
                continue
            if previous.get("routingTarget") != current_key.get("routingTarget"):
                continue
            reasons = invalidation_reasons(previous, current_key)
            if reasons:
                entry["status"] = "Invalidated"
                entry["invalidatedAt"] = now
                entry["invalidationReasons"] = reasons
                invalidated += 1
        return invalidated

    def _metrics(self) -> dict[str, Any]:
        stored = self.metrics_store.read().get("metrics")
        defaults = {
            "cacheVersion": PROMPT_CACHE_VERSION,
            "requests": 0,
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "invalidations": 0,
            "generationsAvoided": 0,
            "estimatedGenerationMsSaved": 0.0,
            "estimatedTokensSaved": 0,
        }
        if isinstance(stored, dict):
            defaults.update(stored)
        return defaults

    def _record_metrics(self, **increments: float) -> None:
        metrics = self._metrics()
        for field, value in increments.items():
            metrics[field] = round(float(metrics.get(field) or 0) + float(value), 2)
            if field not in {"estimatedGenerationMsSaved"}:
                metrics[field] = int(metrics[field])
        self.metrics_store.write({"metrics": metrics})

    def _event(self, event_type: str, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({
                "eventType": event_type,
                "source": "API",
                "correlationId": correlation_id,
                "payload": payload,
            })
