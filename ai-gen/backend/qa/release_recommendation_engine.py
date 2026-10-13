"""Release recommendation from QA readiness."""

from __future__ import annotations

from typing import Any


class ReleaseRecommendationEngine:
    def recommend(self, readiness: dict[str, Any], risks: dict[str, Any], gaps: dict[str, Any]) -> dict[str, Any]:
        status = readiness.get("status")
        if status == "Ready":
            recommendation = "Ready For Release"
        elif status == "Needs Review":
            recommendation = "Ready With Warnings" if readiness.get("overallReadiness", 0) >= 80 else "Needs More Testing"
        else:
            recommendation = "Blocked"
        reasons = []
        if gaps.get("untestedAcceptanceCriteria"):
            reasons.append("Acceptance criteria are not fully covered.")
        if gaps.get("missingPermissionOrSecurity"):
            reasons.append("Permission or security tests are missing.")
        if risks.get("highestRisk") in {"High", "Critical"}:
            reasons.append(f"{risks.get('highestRisk')} QA risk remains.")
        if not reasons:
            reasons.append("QA readiness and coverage meet release threshold.")
        actions = _actions(recommendation, gaps, risks)
        return {
            "recommendation": recommendation,
            "reason": " ".join(reasons),
            "recommendedActions": actions,
        }


def _actions(recommendation: str, gaps: dict[str, Any], risks: dict[str, Any]) -> list[str]:
    actions = []
    if gaps.get("untestedAcceptanceCriteria"):
        actions.append("Generate missing tests for uncovered acceptance criteria.")
    if gaps.get("missingPermissionOrSecurity"):
        actions.append("Run permission and security validation.")
    if risks.get("highestRisk") in {"High", "Critical"}:
        actions.append("Mitigate high-risk QA areas and rerun QA Intelligence.")
    if not actions and recommendation == "Ready For Release":
        actions.append("Proceed with release approval.")
    return actions or ["Repeat QA after resolving warnings."]
