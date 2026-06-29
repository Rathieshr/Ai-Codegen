from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import string_list

VAGUE_PATTERNS = ["should work", "works correctly", "user friendly", "fast enough", "as expected", "properly", "visible and testable"]
MEASURABLE_TERMS = ["given", "when", "then", "can", "within", "receives", "shows", "displays", "returns", "filters", "creates", "prevents", "denied"]


def validate_acceptance_criteria(artifact: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    criteria = string_list(artifact.get("acceptanceCriteria") or artifact.get("acceptance_criteria"))
    issues: list[ValidationIssue] = []
    if not criteria:
        return 20, [
            ValidationIssue(
                "Error",
                "Acceptance Criteria",
                "Artifact has no acceptance criteria.",
                "Add measurable, testable acceptance criteria before approval.",
            )
        ]
    score = 55 + min(len(criteria), 4) * 8
    vague = [item for item in criteria if any(pattern in item.lower() for pattern in VAGUE_PATTERNS)]
    unmeasurable = [item for item in criteria if not any(term in item.lower() for term in MEASURABLE_TERMS)]
    if vague:
        score -= len(vague) * 18
        issues.append(ValidationIssue("Error", "Acceptance Criteria", f"Vague acceptance criteria found: {vague[0]}", "Replace vague wording with observable behavior and expected outcome."))
    if unmeasurable:
        score -= min(len(unmeasurable), 3) * 10
        issues.append(ValidationIssue("Warning", "Acceptance Criteria", "Some acceptance criteria are not clearly measurable.", "Use Given/When/Then or explicit observable outcomes."))
    return max(0, min(score, 100)), issues

