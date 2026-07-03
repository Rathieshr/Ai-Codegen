"""Engineering compliance scoring."""

from __future__ import annotations

from typing import Any

from .types import clamp, number


class ComplianceEngine:
    def validate(self, artifact: dict[str, Any], context: dict[str, Any], policy_result: dict[str, Any] | None = None) -> dict[str, Any]:
        policy_result = policy_result or {}
        scores = {
            "planning": self._planning_score(artifact, context),
            "architecture": number(context.get("architectureCompliance"), 80),
            "codingStandards": number(context.get("codingStandardsCompliance"), 80),
            "repository": number(context.get("repositoryConfidence"), 75),
            "security": number(context.get("securityCompliance"), 80),
            "qa": number(context.get("qa", {}).get("acceptanceCoverage") or context.get("qaCoverage"), 0 if context.get("qa") else 75),
            "release": self._release_score(context),
        }
        violation_penalty = len(policy_result.get("violations", [])) * 12
        warning_penalty = len(policy_result.get("warnings", [])) * 4
        score = clamp(sum(scores.values()) / len(scores) - violation_penalty - warning_penalty)
        if score >= 85:
            status = "Compliant"
        elif score >= 70:
            status = "NeedsReview"
        else:
            status = "NonCompliant"
        return {
            "status": status,
            "score": round(score, 2),
            "scores": {key: round(clamp(value), 2) for key, value in scores.items()},
            "findings": list(policy_result.get("violations", [])) + list(policy_result.get("warnings", [])),
        }

    def _planning_score(self, artifact: dict[str, Any], context: dict[str, Any]) -> float:
        status = str(artifact.get("approvalStatus") or artifact.get("status") or context.get("approvalStatus") or "").lower()
        if status in {"approved", "locked", "passed"}:
            return 95
        if status in {"ready for review", "ready_for_review", "draft"}:
            return 75
        return 60

    def _release_score(self, context: dict[str, Any]) -> float:
        if not context.get("release"):
            return 75
        checks = [
            str(context.get("qaStatus") or "").lower() in {"ready", "passed", "release ready"},
            str(context.get("validationStatus") or "").lower() in {"passed", "approved"},
            str(context.get("prReviewStatus") or "").lower() in {"completed", "passed", "approved"},
        ]
        return 100 * (sum(1 for item in checks if item) / len(checks))
