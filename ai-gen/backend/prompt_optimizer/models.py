"""Canonical Prompt Optimizer contracts."""

from __future__ import annotations

from typing import Any, TypedDict


PROMPT_OPTIMIZER_VERSION = "1.0"
SUPPORTED_PROMPT_MODES = (
    "implementation",
    "bug_fix",
    "refactor",
    "architecture",
    "review",
    "documentation",
    "testing",
    "optimization",
)


class OptimizedPromptSection(TypedDict):
    id: str
    order: int
    title: str
    content: Any
    rendered: str
    placement: str


class OptimizedExecutionPrompt(TypedDict):
    optimizedPromptId: str
    optimizerVersion: str
    sourceExecutionPromptId: str
    sourceBudgetedPromptId: str
    sourceCompiledPromptId: str
    sourceExecutionManifestId: str
    modelId: str
    provider: str
    mode: str
    systemPrompt: str | None
    prompt: str
    sections: list[OptimizedPromptSection]
    appendix: list[OptimizedPromptSection]
    estimatedTokens: int
    maxInputTokens: int
    promptQualityScore: int
    promptConfidence: float
    status: str
    warnings: list[str]
    immutable: bool
    immutableHash: str
    optimizedAt: str
    diagnostics: dict[str, Any]
