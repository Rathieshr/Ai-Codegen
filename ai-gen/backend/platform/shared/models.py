"""Shared models and normalization helpers for the HEI platform foundation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class OperationStatus(str, Enum):
    PENDING = "Pending"
    QUEUED = "Queued"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    NEEDS_APPROVAL = "NeedsApproval"
    SKIPPED = "Skipped"


class OperationPriority(str, Enum):
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    CRITICAL = "Critical"


class OperationSource(str, Enum):
    MANUAL = "Manual"
    SCHEDULER = "Scheduler"
    AZURE_DEVOPS = "AzureDevOps"
    GIT = "Git"
    VSCODE = "VSCode"
    API = "API"
    AGENT = "Agent"
    EXECUTION_RUNTIME = "ExecutionRuntime"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value: Any) -> str:
    return str(value or "").strip()


def as_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = clean(value)
        if text:
            result.append(text)
    return result


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def enum_value(value: Any, enum_type: type[Enum], default: Enum) -> str:
    text = clean(value)
    for member in enum_type:
        if member.value == text:
            return member.value
    return default.value


def platform_result(
    success: bool,
    *,
    status: OperationStatus | str = OperationStatus.COMPLETED,
    message: str = "",
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": bool(success),
        "status": enum_value(status, OperationStatus, OperationStatus.COMPLETED if success else OperationStatus.FAILED),
        "message": clean(message),
        "errors": as_string_list(errors or []),
        "warnings": as_string_list(warnings or []),
        "metadata": as_dict(metadata),
    }


def progress_state(progress: dict[str, Any] | None = None) -> dict[str, Any]:
    progress = progress or {}
    completed = as_string_list(progress.get("completedSteps"))
    pending = as_string_list(progress.get("pendingSteps"))
    percent = progress.get("percentComplete", 0)
    try:
        numeric_percent = max(0, min(100, int(float(percent))))
    except (TypeError, ValueError):
        numeric_percent = 0
    return {
        "currentStep": clean(progress.get("currentStep")),
        "completedSteps": completed,
        "pendingSteps": pending,
        "percentComplete": numeric_percent,
        "startedAt": clean(progress.get("startedAt")),
        "updatedAt": clean(progress.get("updatedAt")) or now_iso(),
    }


def generated_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
