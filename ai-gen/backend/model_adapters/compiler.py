"""Public, provider-free ExecutionPrompt compilation service."""

from __future__ import annotations

from typing import Any

from backend.model_registry import ModelRegistry

from .registry import ModelAdapterRegistry


class ModelAdapterCompiler:
    def __init__(self, *, model_registry: ModelRegistry | None = None, adapter_registry: ModelAdapterRegistry | None = None) -> None:
        self.model_registry = model_registry or ModelRegistry()
        self.adapter_registry = adapter_registry or ModelAdapterRegistry()

    def compile(self, budgeted_prompt: dict[str, Any], model_id: str) -> dict[str, Any]:
        normalized_id = str(model_id or "").strip().casefold()
        profile = self.model_registry.get(normalized_id)
        if not profile:
            raise ValueError(f"Unknown model profile: {normalized_id or '<missing>'}.")
        adapter = self.adapter_registry.get(normalized_id)
        if not adapter:
            raise ValueError(f"No Model Adapter is registered for {normalized_id}.")
        return adapter.compile(budgeted_prompt, profile)

    def supported_models(self) -> list[str]:
        return self.adapter_registry.list_ids()


def compile_execution_prompt(budgeted_prompt: dict[str, Any], model_id: str) -> dict[str, Any]:
    return ModelAdapterCompiler().compile(budgeted_prompt, model_id)
