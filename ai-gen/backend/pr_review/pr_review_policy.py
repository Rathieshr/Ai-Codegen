"""Feature flags and policy for PR Review V1."""

from __future__ import annotations

import os
from typing import Any


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "false")).strip().lower() in {"1", "true", "yes", "on"}


def pr_review_flags() -> dict[str, bool]:
    return {
        "ENABLE_PR_REVIEW": _enabled("ENABLE_PR_REVIEW"),
        "ENABLE_PR_COMMENT_POSTING": _enabled("ENABLE_PR_COMMENT_POSTING"),
    }


class PRReviewPolicy:
    def __init__(self, flags: dict[str, bool] | None = None) -> None:
        self.flags = flags or pr_review_flags()

    def status_for(self, implementation_report: dict[str, Any], linked_work_items: list[dict[str, Any]], execution_package: dict[str, Any]) -> str:
        if not linked_work_items:
            return "NeedsReview"
        if not execution_package:
            return "NeedsReview"
        violations = implementation_report.get("violations") or []
        critical_rules = {str(item.get("rule") or "") for item in violations if item.get("severity") == "critical"}
        blocking_rules = {str(item.get("rule") or "") for item in violations if item.get("rule") in {"blocked_scope_modified", "acceptance_criteria_coverage"}}
        if critical_rules or blocking_rules or implementation_report.get("status") == "Failed":
            return "Blocked"
        if int(implementation_report.get("testCoverageScore") or 0) < 80:
            return "NeedsReview"
        if int(implementation_report.get("acceptanceCoverageScore") or 0) < 80:
            return "Blocked"
        if implementation_report.get("status") == "Passed":
            return "Passed"
        return "NeedsReview"

    def posting_enabled(self) -> bool:
        return bool(self.flags.get("ENABLE_PR_COMMENT_POSTING"))
