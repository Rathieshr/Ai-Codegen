"""Generate Azure DevOps PR review comment text."""

from __future__ import annotations

from typing import Any


class PRReviewCommentBuilder:
    def build(self, report: dict[str, Any]) -> str:
        blocking = report.get("blockingIssues") or []
        warnings = report.get("warnings") or []
        recommendations = report.get("recommendations") or []
        scores = report.get("scores") or {}
        lines = [
            "## HEI PR Review",
            "",
            f"Status: {report.get('status') or 'NeedsReview'}",
            "",
            "Summary:",
            report.get("summary") or "HEI reviewed this PR against the approved execution context.",
            "",
            "Scores:",
            f"- Acceptance Coverage: {scores.get('acceptanceCoverage', 0)}%",
            f"- Scope Compliance: {scores.get('scopeCompliance', 0)}%",
            f"- Repository Alignment: {scores.get('repositoryAlignment', 0)}%",
            f"- Standards: {scores.get('standards', 0)}%",
            f"- Tests: {scores.get('tests', 0)}%",
            "",
            "Blocking Issues:",
        ]
        lines.extend([f"- {item}" for item in blocking] if blocking else ["- None"])
        lines.extend(["", "Warnings:"])
        lines.extend([f"- {item}" for item in warnings] if warnings else ["- None"])
        lines.extend(["", "Recommended Action:", recommendations[0] if recommendations else "No immediate action required."])
        return "\n".join(lines)
