"""Diagnostics helpers for PR Review V1."""

from __future__ import annotations

from typing import Any

from backend.implementation_validation.models import now_iso


def pr_review_diagnostics(
    *,
    flags: dict[str, bool],
    linked_items: list[dict[str, Any]],
    diff: dict[str, Any],
    execution_package: dict[str, Any],
    implementation_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generatedAt": now_iso(),
        "flags": flags,
        "linkedWorkItemCount": len(linked_items),
        "changedFileCount": len(diff.get("changedFiles") or []),
        "diffSource": diff.get("source") or "none",
        "executionPackageLoaded": bool(execution_package),
        "implementationValidationStatus": implementation_report.get("status"),
        "implementationValidationReportId": implementation_report.get("reportId"),
    }
