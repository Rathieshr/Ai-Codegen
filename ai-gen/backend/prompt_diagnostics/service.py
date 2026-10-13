"""Persistent application service for immutable Prompt Diagnostics artifacts."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore

from .builder import PromptDiagnosticsBuilder


class PromptDiagnosticsService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        model_registry: Any,
        builder: PromptDiagnosticsBuilder | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.model_registry = model_registry
        self.builder = builder or PromptDiagnosticsBuilder()
        self.platform = platform

    def build(
        self,
        optimized_prompt: dict[str, Any],
        execution_manifest: dict[str, Any],
        execution_package: dict[str, Any] | None = None,
        estimation_profile: dict[str, Any] | None = None,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        model_profile = self.model_registry.get(str(optimized_prompt.get("modelId") or ""))
        artifact = self.builder.build(
            optimized_prompt,
            execution_manifest,
            execution_package,
            model_profile,
            estimation_profile,
        )
        values = self.store.read()
        existing = values.get(artifact["diagnosticsId"])
        if existing:
            if existing.get("immutableHash") != artifact.get("immutableHash"):
                raise ValueError("Prompt Diagnostics identity collision detected.")
            return deepcopy(existing)
        artifact["diagnostics"]["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        values[artifact["diagnosticsId"]] = artifact
        self.store.write(values)
        self._event("PromptDiagnosticsGenerated", correlation_id, {
            "diagnosticsId": artifact["diagnosticsId"],
            "optimizedPromptId": artifact["optimizedPromptId"],
            "executionManifestId": artifact["executionManifestId"],
            "model": artifact["model"]["id"],
        })
        return deepcopy(artifact)

    def get(self, diagnostics_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(diagnostics_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def get_by_prompt(self, optimized_prompt_id: str) -> dict[str, Any] | None:
        for value in self.store.read().values():
            if isinstance(value, dict) and value.get("optimizedPromptId") == optimized_prompt_id:
                return deepcopy(value)
        return None

    def summary(self, diagnostics_id: str) -> dict[str, Any] | None:
        value = self.get(diagnostics_id)
        if not value:
            return None
        return {
            "diagnosticsId": value["diagnosticsId"],
            "optimizedPromptId": value["optimizedPromptId"],
            "executionManifestVersion": value["executionManifestVersion"],
            "executionPackageVersion": value["executionPackageVersion"],
            "repositorySnapshot": value["repositorySnapshot"],
            "knowledgeVersion": value["knowledgeVersion"],
            "memoryVersion": value["memoryVersion"],
            "model": value["model"],
            "tokenCount": value["tokenCount"],
            "optimizationRatio": value["optimizationRatio"],
            "confidence": value["confidence"],
            "warningCount": len(value["warnings"]),
            "filesIncluded": len(value["filesIncluded"]),
            "filesExcluded": len(value["filesExcluded"]),
            "estimatedCost": value["estimatedCost"],
            "estimatedDuration": value["estimatedDuration"],
        }

    def _event(self, event_type: str, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({
                "eventType": event_type,
                "source": "API",
                "correlationId": correlation_id,
                "payload": payload,
            })
