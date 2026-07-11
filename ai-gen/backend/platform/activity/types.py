"""Activity log models for the platform foundation."""

from __future__ import annotations

from typing import Any

from ..shared import OperationSource, as_dict, clean, enum_value, generated_id, now_iso


def normalize_activity_log_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "activityId": clean(entry.get("activityId") or entry.get("id")) or generated_id("activity"),
        "activityType": clean(entry.get("activityType") or entry.get("type")) or "PlatformActivity",
        "title": clean(entry.get("title")) or "Platform activity",
        "description": clean(entry.get("description")),
        "source": enum_value(entry.get("source"), OperationSource, OperationSource.API),
        "actor": clean(entry.get("actor")),
        "projectId": clean(entry.get("projectId")),
        "repositoryId": clean(entry.get("repositoryId")),
        "workItemId": clean(entry.get("workItemId")),
        "correlationId": clean(entry.get("correlationId")) or generated_id("corr"),
        "metadata": as_dict(entry.get("metadata")),
        "createdAt": clean(entry.get("createdAt")) or now_iso(),
    }
