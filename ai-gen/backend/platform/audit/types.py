"""Audit models for the platform foundation."""

from __future__ import annotations

from typing import Any

from ..shared import OperationSource, as_dict, clean, enum_value, generated_id, now_iso


def normalize_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "auditId": clean(event.get("auditId") or event.get("id")) or generated_id("audit"),
        "action": clean(event.get("action")) or "PlatformAudit",
        "actor": clean(event.get("actor")) or "system",
        "source": enum_value(event.get("source"), OperationSource, OperationSource.API),
        "targetType": clean(event.get("targetType")) or "Artifact",
        "targetId": clean(event.get("targetId")),
        "before": as_dict(event.get("before")) if isinstance(event.get("before"), dict) else event.get("before"),
        "after": as_dict(event.get("after")) if isinstance(event.get("after"), dict) else event.get("after"),
        "reason": clean(event.get("reason")),
        "correlationId": clean(event.get("correlationId")) or generated_id("corr"),
        "createdAt": clean(event.get("createdAt")) or now_iso(),
    }
