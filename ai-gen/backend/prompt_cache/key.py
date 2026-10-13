"""Canonical Prompt Cache key construction and lineage comparison."""

from __future__ import annotations

from typing import Any

from backend.token_intelligence.models import stable_hash

from .models import PromptCacheKey


_INVALIDATION_FIELDS = {
    "executionManifestIdentity": "Execution Manifest changed.",
    "executionPackageId": "Execution Package changed.",
    "executionPackageVersion": "Execution Package version changed.",
    "repositorySnapshotVersion": "Repository Snapshot changed.",
    "knowledgeVersion": "Knowledge Version changed.",
    "memoryVersion": "Engineering Memory Version changed.",
    "modelId": "Selected model changed.",
    "executionMode": "Execution Mode changed.",
    "routingTarget": "Routing target changed.",
}


def build_cache_key(
    execution_manifest: dict[str, Any],
    *,
    model_id: str,
    execution_mode: str,
    routing_target: str,
) -> tuple[str, PromptCacheKey]:
    source = execution_manifest.get("sourceVersions") if isinstance(execution_manifest.get("sourceVersions"), dict) else {}
    key: PromptCacheKey = {
        "executionManifestVersion": str(execution_manifest.get("manifestVersion") or ""),
        "executionManifestIdentity": str(execution_manifest.get("immutableHash") or execution_manifest.get("manifestId") or ""),
        "executionPackageId": str(execution_manifest.get("sourcePackageId") or ""),
        "executionPackageVersion": str(source.get("executionPackageVersion") or ""),
        "repositorySnapshotVersion": str(source.get("repositorySnapshotVersion") or ""),
        "knowledgeVersion": str(source.get("knowledgeVersion") or ""),
        "memoryVersion": str(source.get("engineeringMemoryVersion") or ""),
        "modelId": str(model_id or "").strip().casefold(),
        "executionMode": str(execution_mode or "").strip().casefold(),
        "routingTarget": str(routing_target or "").strip().casefold(),
    }
    return f"promptcache_{stable_hash(key)[:16]}", key


def invalidation_reasons(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return [reason for field, reason in _INVALIDATION_FIELDS.items() if previous.get(field) != current.get(field)]


def missing_lineage(key: dict[str, Any]) -> list[str]:
    required = (
        "executionManifestVersion",
        "executionManifestIdentity",
        "executionPackageId",
        "executionPackageVersion",
        "repositorySnapshotVersion",
        "knowledgeVersion",
        "memoryVersion",
        "modelId",
        "executionMode",
    )
    return [field for field in required if not key.get(field)]
