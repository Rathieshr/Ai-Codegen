"""Prompt Cache contracts."""

from __future__ import annotations

from typing import Any, TypedDict


PROMPT_CACHE_VERSION = "1.0"


class PromptCacheKey(TypedDict):
    executionManifestVersion: str
    executionManifestIdentity: str
    executionPackageId: str
    executionPackageVersion: str
    repositorySnapshotVersion: str
    knowledgeVersion: str
    memoryVersion: str
    modelId: str
    executionMode: str
    routingTarget: str


class PromptCacheEntry(TypedDict):
    cacheKey: str
    cacheVersion: str
    key: PromptCacheKey
    status: str
    routingId: str
    routingResult: dict[str, Any]
    estimatedTokens: int
    generationDurationMs: float
    hitCount: int
    createdAt: str
    lastAccessedAt: str
    invalidatedAt: str
    invalidationReasons: list[str]
