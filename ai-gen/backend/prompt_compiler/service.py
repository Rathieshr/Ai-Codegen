"""Persistent application service for immutable CompiledPrompt artifacts."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore

from .compiler import PromptCompiler


class PromptCompilerService:
    def __init__(self, store: JsonMapStore, *, compiler: PromptCompiler | None = None, platform: Any | None = None) -> None:
        self.store = store
        self.compiler = compiler or PromptCompiler()
        self.platform = platform

    def compile(self, manifest: dict[str, Any], correlation_id: str = "") -> dict[str, Any]:
        started = time.perf_counter()
        manifest_id = str(manifest.get("manifestId") or "")
        self._event("PromptCompilationRequested", correlation_id, {"manifestId": manifest_id})
        compiled = self.compiler.compile(manifest)
        values = self.store.read()
        existing = values.get(compiled["compiledPromptId"])
        if existing:
            if existing.get("immutableHash") != compiled.get("immutableHash"):
                raise ValueError("Compiled Prompt identity collision detected.")
            self._event("CompiledPromptReused", correlation_id, {"compiledPromptId": compiled["compiledPromptId"], "manifestId": manifest_id})
            return deepcopy(existing)
        compiled["diagnostics"]["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        values[compiled["compiledPromptId"]] = compiled
        self.store.write(values)
        self._event("PromptCompilationCompleted", correlation_id, {"compiledPromptId": compiled["compiledPromptId"], "manifestId": manifest_id})
        return deepcopy(compiled)

    def get(self, compiled_prompt_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(compiled_prompt_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def _event(self, event_type: str, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "API", "correlationId": correlation_id, "payload": payload})
