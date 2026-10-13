"""Canonical Prompt Diagnostics contracts."""

from __future__ import annotations

from typing import Any, TypedDict


PROMPT_DIAGNOSTICS_VERSION = "1.0"


class PromptFileDiagnostic(TypedDict, total=False):
    path: str
    confidence: float | None
    reason: str
    source: str


class PromptDiagnostics(TypedDict):
    diagnosticsId: str
    diagnosticsVersion: str
    optimizedPromptId: str
    executionPromptId: str
    executionManifestId: str
    executionManifestVersion: str
    executionPackageId: str
    executionPackageVersion: str
    repositorySnapshot: str
    knowledgeVersion: str
    memoryVersion: str
    model: dict[str, Any]
    promptSize: dict[str, int]
    tokenCount: dict[str, Any]
    optimizationRatio: float
    optimizationReductionPercent: float
    confidence: float
    promptQualityScore: int
    warnings: list[str]
    filesIncluded: list[PromptFileDiagnostic]
    filesExcluded: list[PromptFileDiagnostic]
    estimatedCost: dict[str, Any]
    estimatedDuration: dict[str, Any]
    immutable: bool
    immutableHash: str
    generatedAt: str
    diagnostics: dict[str, Any]
