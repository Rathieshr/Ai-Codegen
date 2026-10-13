"""Model-neutral Prompt Compiler contracts and normalization helpers."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, TypedDict


COMPILER_VERSION = "1.0"
SECTION_ORDER = (
    "business_objective",
    "repository_context",
    "implementation_guidance",
    "validation",
    "qa",
    "constraints",
    "instructions",
)


class CompiledPromptSection(TypedDict):
    id: str
    order: int
    title: str
    content: Any
    sourceFields: list[str]


class CompiledPrompt(TypedDict):
    compiledPromptId: str
    compilerVersion: str
    executionManifestId: str
    sourcePackageId: str
    sections: list[CompiledPromptSection]
    warnings: list[str]
    immutable: bool
    immutableHash: str
    compiledAt: str
    diagnostics: dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def sequence(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
