"""Trace model normalization."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


TRACE_STAGES = ["Planning", "Execution", "Validation", "QA", "Memory"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
    if isinstance(value, dict):
        text = clean(value.get("name") or value.get("title") or value.get("id") or value.get("path"))
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(string_list(item))
        return unique(output)
    text = clean(value)
    return [text] if text else []


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = clean(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def normalize_trace(value: dict[str, Any]) -> dict[str, Any]:
    stage = clean(value.get("stage") or value.get("source") or "Planning").title()
    if stage.upper() == "QA":
        stage = "QA"
    if stage not in TRACE_STAGES:
        stage = "Planning"
    artifact = value.get("artifact") if isinstance(value.get("artifact"), dict) else {}
    artifact_id = clean(value.get("artifactId") or value.get("artifact_id") or artifact.get("id"))
    artifact_type = clean(value.get("artifactType") or value.get("artifact_type") or artifact.get("type"))
    decision = clean(value.get("decision") or value.get("title") or "Decision")
    created_at = clean(value.get("time") or value.get("createdAt") or value.get("created_at") or now_iso())
    fingerprint = hashlib.sha256(
        "|".join([
            clean(value.get("projectId") or value.get("project_id") or "default"),
            artifact_type,
            artifact_id,
            stage,
            decision,
            clean(value.get("reason")),
            created_at,
        ]).encode("utf-8")
    ).hexdigest()
    trace_id = clean(value.get("id") or value.get("traceId") or f"trace_{fingerprint[:12]}")
    return {
        "id": trace_id,
        "traceId": trace_id,
        "projectId": clean(value.get("projectId") or value.get("project_id") or "default"),
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "artifactTitle": clean(value.get("artifactTitle") or artifact.get("title")),
        "stage": stage,
        "source": clean(value.get("source") or stage),
        "decision": decision,
        "reason": clean(value.get("reason")),
        "confidence": float(value.get("confidence", 0.0) or 0.0),
        "evidence": _object_list(value.get("evidence")),
        "promptVersion": clean(value.get("promptVersion") or value.get("prompt_version")),
        "memoryUsed": _object_list(value.get("memoryUsed") or value.get("memory_used")),
        "repositoryEvidence": _object_list(value.get("repositoryEvidence") or value.get("repository_evidence")),
        "graphEvidence": _object_list(value.get("graphEvidence") or value.get("graph_evidence")),
        "validationResult": value.get("validationResult") or value.get("validation_result") or {},
        "time": created_at,
        "latencyMs": int(value.get("latencyMs") or value.get("latency_ms") or 0),
        "model": clean(value.get("model")),
        "tokenUsage": value.get("tokenUsage") if isinstance(value.get("tokenUsage"), dict) else {},
        "tags": unique(string_list(value.get("tags")) + [stage, artifact_type, decision]),
        "metadata": value.get("metadata") if isinstance(value.get("metadata"), dict) else {},
    }


def _object_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
