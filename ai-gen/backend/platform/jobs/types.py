"""Platform job models and normalization helpers."""

from __future__ import annotations

from typing import Any

from ..shared import (
    OperationPriority,
    OperationSource,
    OperationStatus,
    as_dict,
    clean,
    enum_value,
    generated_id,
    now_iso,
    progress_state,
)


def normalize_platform_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobId": clean(job.get("jobId") or job.get("id")) or generated_id("platform_job"),
        "jobType": clean(job.get("jobType") or job.get("type")) or "PlatformJob",
        "source": enum_value(job.get("source"), OperationSource, OperationSource.MANUAL),
        "priority": enum_value(job.get("priority"), OperationPriority, OperationPriority.NORMAL),
        "status": enum_value(job.get("status"), OperationStatus, OperationStatus.QUEUED),
        "correlationId": clean(job.get("correlationId")) or generated_id("corr"),
        "payload": as_dict(job.get("payload")),
        "result": as_dict(job.get("result")),
        "progress": progress_state(job.get("progress")),
        "retryCount": int(job.get("retryCount") or 0),
        "maxRetries": max(0, int(job.get("maxRetries") or 0)),
        "createdAt": clean(job.get("createdAt")) or now_iso(),
        "startedAt": clean(job.get("startedAt")),
        "completedAt": clean(job.get("completedAt")),
        "failedAt": clean(job.get("failedAt")),
        "error": clean(job.get("error")),
    }


def is_terminal(status: str) -> bool:
    return status in {
        OperationStatus.COMPLETED.value,
        OperationStatus.FAILED.value,
        OperationStatus.CANCELLED.value,
        OperationStatus.SKIPPED.value,
    }
