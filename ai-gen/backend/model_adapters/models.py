"""Canonical Model Adapter and ExecutionPrompt contracts."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


MODEL_ADAPTER_VERSION = "1.0"


class AdaptedPromptSection(TypedDict):
    id: str
    order: int
    title: str
    content: Any
    rendered: str


class ExecutionPrompt(TypedDict):
    executionPromptId: str
    promptVersion: str
    modelId: str
    provider: str
    sourceBudgetedPromptId: str
    sourceCompiledPromptId: str
    sourceExecutionManifestId: str
    systemPrompt: str | None
    adapterObjective: str
    modelInstructions: list[str]
    prompt: str
    sections: list[AdaptedPromptSection]
    estimatedTokens: int
    maxInputTokens: int
    status: str
    warnings: list[str]
    immutable: bool
    immutableHash: str
    generatedAt: str
    diagnostics: dict[str, Any]


class IModelAdapter(Protocol):
    model_id: str
    prompt_version: str

    def compile(self, budgeted_prompt: dict[str, Any], model_profile: dict[str, Any]) -> ExecutionPrompt: ...
