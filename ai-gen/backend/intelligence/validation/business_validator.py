from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import artifact_text, clean, context_text, score_from_overlap


def validate_business_alignment(planning_context: dict[str, Any], artifact: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    score = score_from_overlap(artifact_text(artifact), context_text(planning_context), base=38)
    issues: list[ValidationIssue] = []
    if not clean(artifact.get("businessValue") or artifact.get("business_value")):
        score -= 20
        issues.append(
            ValidationIssue(
                "Warning",
                "Business Alignment",
                "Artifact does not explain business value.",
                "Add business value tied to the parent business objective.",
            )
        )
    if score < 45:
        issues.append(
            ValidationIssue(
                "Error",
                "Business Alignment",
                "Artifact has weak alignment to the parent business objective.",
                "Regenerate using the supplied PlanningContext or revise the artifact scope.",
            )
        )
    return max(0, score), issues

