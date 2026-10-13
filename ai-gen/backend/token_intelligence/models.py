"""Contracts for deterministic, model-independent token intelligence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, TypedDict


TOKEN_INTELLIGENCE_VERSION = "1.0"
SUPPORTED_TOKEN_BUDGETS = (1024, 2048, 4096, 8192, 16000, 32000, 128000)
DEFAULT_OUTPUT_RESERVES = {
    1024: 256,
    2048: 384,
    4096: 768,
    8192: 1024,
    16000: 2048,
    32000: 4096,
    128000: 8192,
}


class RemovedContext(TypedDict):
    sectionId: str
    path: str
    estimatedTokens: int
    reason: str
    valueHash: str
    valuePreview: str


class BudgetedPrompt(TypedDict):
    budgetedPromptId: str
    tokenIntelligenceVersion: str
    compiledPromptId: str
    executionManifestId: str
    requestedBudgetTokens: int
    reservedOutputTokens: int
    inputBudgetTokens: int
    sections: list[dict[str, Any]]
    status: str
    immutable: bool
    immutableHash: str
    optimizedAt: str
    diagnostics: dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def estimate_tokens(value: Any) -> int:
    """Estimate tokens from canonical JSON using HEI's four-characters heuristic."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return max(1, (len(payload) + 3) // 4)
