"""Execution Manifest model helpers."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, TypedDict


MANIFEST_VERSION = "1.0"


class ExecutionManifest(TypedDict):
    manifestId: str
    manifestVersion: str
    sourcePackageId: str
    sourceVersions: dict[str, Any]
    objective: str
    businessGoal: str
    acceptanceCriteria: list[dict[str, Any]]
    repositoryContext: dict[str, Any]
    relevantFiles: list[Any]
    dependencies: list[str]
    implementationGuidance: dict[str, Any]
    validationGuidance: dict[str, Any]
    qaGuidance: dict[str, Any]
    engineeringStandards: list[Any]
    risks: list[Any]
    warnings: list[str]
    confidence: float
    tokenEstimates: dict[str, Any]
    immutable: bool
    immutableHash: str
    generatedAt: str
    diagnostics: dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def items(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return unique([value])
    if isinstance(value, dict):
        return unique([clean(value.get("name") or value.get("title") or value.get("rule") or value.get("risk"))])
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                result.append(clean(item.get("name") or item.get("title") or item.get("rule") or item.get("risk") or item.get("content")))
            else:
                result.append(clean(item))
        return unique(result)
    return unique([clean(value)])


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = clean(value)
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
