"""Assemble PR Review report payloads."""

from __future__ import annotations

from typing import Any

from backend.implementation_validation.models import now_iso, stable_id


def build_pr_review_report(
    *,
    status: str,
    pull_request: dict[str, Any],
    linked_work_items: list[dict[str, Any]],
    implementation_report: dict[str, Any],
    diagnostics: dict[str, Any],
    posting_enabled: bool,
) -> dict[str, Any]:
    violations = implementation_report.get("violations") or []
    blocking = [
        item.get("message") or item.get("rule") or "Blocking implementation issue."
        for item in violations
        if item.get("severity") == "critical" or item.get("rule") in {"blocked_scope_modified", "acceptance_criteria_coverage"}
    ]
    warnings = [
        item.get("message") or item.get("rule") or "Review warning."
        for item in violations
        if item.get("severity") != "critical" and item.get("rule") not in {"blocked_scope_modified", "acceptance_criteria_coverage"}
    ]
    if not linked_work_items:
        warnings.append("No linked Azure DevOps work item was supplied for this PR.")
    score = _validation_score(implementation_report)
    summary = _summary(status, implementation_report, linked_work_items)
    report = {
        "reportId": stable_id("prreview", {"pr": pull_request.get("id") or pull_request.get("pullRequestId"), "impl": implementation_report.get("reportId")}),
        "pullRequestId": pull_request.get("id") or pull_request.get("pullRequestId"),
        "status": status,
        "summary": summary,
        "linkedWorkItems": linked_work_items,
        "validationScore": score,
        "scores": {
            "acceptanceCoverage": int(implementation_report.get("acceptanceCoverageScore") or 0),
            "scopeCompliance": int(implementation_report.get("scopeComplianceScore") or 0),
            "repositoryAlignment": int(implementation_report.get("repositoryAlignmentScore") or 0),
            "standards": int(implementation_report.get("standardsComplianceScore") or 0),
            "tests": int(implementation_report.get("testCoverageScore") or 0),
        },
        "blockingIssues": blocking,
        "warnings": warnings,
        "changedFiles": implementation_report.get("changedFiles") or [],
        "implementationValidation": implementation_report,
        "recommendations": implementation_report.get("recommendations") or [],
        "generatedReviewComment": "",
        "commentPostingEnabled": posting_enabled,
        "diagnostics": diagnostics,
        "generatedAt": now_iso(),
    }
    return report


def _validation_score(report: dict[str, Any]) -> int:
    scores = [
        int(report.get("acceptanceCoverageScore") or 0),
        int(report.get("scopeComplianceScore") or 0),
        int(report.get("repositoryAlignmentScore") or 0),
        int(report.get("standardsComplianceScore") or 0),
        int(report.get("testCoverageScore") or 0),
    ]
    return round(sum(scores) / len(scores)) if scores else 0


def _summary(status: str, report: dict[str, Any], linked_work_items: list[dict[str, Any]]) -> str:
    if not linked_work_items:
        return "This PR needs review because no linked work item was available to verify approved scope."
    if status == "Passed":
        return "This PR satisfies the approved task scope, acceptance coverage, repository alignment, standards, and test expectations."
    if status == "Blocked":
        return "This PR is blocked because implementation changes violate approved scope or acceptance coverage."
    missing = len([item for item in report.get("acceptanceResults") or [] if item.get("status") != "implemented"])
    if missing:
        return f"This PR partially satisfies the approved task, but {missing} acceptance criteria require verification."
    return "This PR needs review before approval."
