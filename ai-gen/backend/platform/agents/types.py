"""Platform agent runtime models."""

from __future__ import annotations

from typing import Any

from ..shared import (
    OperationSource,
    OperationStatus,
    as_dict,
    as_string_list,
    clean,
    enum_value,
    generated_id,
    now_iso,
    progress_state,
)


def normalize_agent_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "agentId": clean(profile.get("agentId") or profile.get("id")) or generated_id("platform_agent"),
        "name": clean(profile.get("name")) or "Platform Agent",
        "description": clean(profile.get("description")),
        "enabled": profile.get("enabled", True) is not False,
        "supportedTriggers": as_string_list(profile.get("supportedTriggers")),
        "requiredPermissions": as_string_list(profile.get("requiredPermissions")),
        "maxRetries": max(0, int(profile.get("maxRetries") or 0)),
        "timeoutSeconds": max(1, int(profile.get("timeoutSeconds") or 60)),
    }


def normalize_agent_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": clean(run.get("runId") or run.get("id")) or generated_id("agent_run"),
        "agentId": clean(run.get("agentId")),
        "triggerEventId": clean(run.get("triggerEventId")),
        "source": enum_value(run.get("source"), OperationSource, OperationSource.AGENT),
        "status": enum_value(run.get("status"), OperationStatus, OperationStatus.PENDING),
        "correlationId": clean(run.get("correlationId")) or generated_id("corr"),
        "input": as_dict(run.get("input")),
        "output": as_dict(run.get("output")),
        "progress": progress_state(run.get("progress")),
        "startedAt": clean(run.get("startedAt")),
        "completedAt": clean(run.get("completedAt")),
        "failedAt": clean(run.get("failedAt")),
        "error": clean(run.get("error")),
    }


def default_agent_context(
    profile: dict[str, Any],
    trigger_event: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "agentProfile": normalize_agent_profile(profile),
        "triggerEvent": as_dict(trigger_event),
        "context": as_dict(context),
        "builtAt": now_iso(),
    }
