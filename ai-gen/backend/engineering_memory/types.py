"""Engineering Memory model normalization."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .policies import MemoryPolicies


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
        text = clean(value.get("name") or value.get("title") or value.get("path") or value.get("id"))
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


def memory_fingerprint(memory: dict[str, Any]) -> str:
    source = "|".join(
        [
            clean(memory.get("projectId")),
            clean(memory.get("category")),
            clean(memory.get("title")).casefold(),
            clean(memory.get("artifactType")),
            clean(memory.get("artifactId")),
            clean(memory.get("summary")).casefold(),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def normalize_memory(value: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    policies = MemoryPolicies()
    existing = existing or {}
    now = now_iso()
    category = policies.normalize_category(value.get("category") or existing.get("category"))
    status = policies.normalize_status(value.get("approvalStatus") or value.get("approval_status") or existing.get("approvalStatus") or "Draft")
    project_id = clean(value.get("projectId") or value.get("project_id") or existing.get("projectId") or "default")
    artifact_type = clean(value.get("artifactType") or value.get("artifact_type") or existing.get("artifactType"))
    artifact_id = clean(value.get("artifactId") or value.get("artifact_id") or existing.get("artifactId"))
    title = clean(value.get("title") or existing.get("title") or artifact_type or category)
    memory = {
        "id": clean(value.get("id") or existing.get("id")),
        "projectId": project_id,
        "category": category,
        "title": title,
        "summary": clean(value.get("summary") or existing.get("summary") or title),
        "content": value.get("content", existing.get("content", "")),
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "repositoryEvidence": value.get("repositoryEvidence") if isinstance(value.get("repositoryEvidence"), list) else existing.get("repositoryEvidence", []),
        "knowledgeReferences": string_list(value.get("knowledgeReferences") or existing.get("knowledgeReferences")),
        "graphReferences": string_list(value.get("graphReferences") or existing.get("graphReferences")),
        "tags": unique(string_list(value.get("tags") or existing.get("tags")) + [category, artifact_type]),
        "confidence": float(value.get("confidence", existing.get("confidence", 0.75)) or 0.0),
        "approvalStatus": status,
        "createdBy": clean(value.get("createdBy") or value.get("created_by") or existing.get("createdBy") or "HEI"),
        "createdAt": clean(existing.get("createdAt") or value.get("createdAt") or value.get("created_at") or now),
        "updatedAt": now,
        "version": int(value.get("version") or existing.get("version") or 1),
        "lastUsedAt": clean(value.get("lastUsedAt") or existing.get("lastUsedAt")),
        "usageCount": int(value.get("usageCount") or existing.get("usageCount") or 0),
        "source": value.get("source") if isinstance(value.get("source"), dict) else existing.get("source", {}),
        "history": existing.get("history", []),
    }
    if isinstance(value.get("index"), dict):
        memory["index"] = value["index"]
    elif isinstance(existing.get("index"), dict):
        memory["index"] = existing["index"]
    fingerprint = memory_fingerprint(memory)
    memory["fingerprint"] = clean(value.get("fingerprint") or existing.get("fingerprint") or fingerprint)
    if not memory["id"]:
        memory["id"] = f"memory_{fingerprint[:12]}"
    return memory
