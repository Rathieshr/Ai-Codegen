from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import clean, string_list


def score_sprint_readiness(artifact: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    title = clean(artifact.get("title"))
    description = clean(artifact.get("description"))
    criteria = string_list(artifact.get("acceptanceCriteria") or artifact.get("acceptance_criteria"))
    text = f"{title} {description}".lower()
    score = 30
    issues: list[ValidationIssue] = []
    if title:
        score += 12
    if "as a " in text and "i want" in text:
        score += 18
    elif artifact.get("artifactType") in {"Feature Recommendation", "Epic Refinement"}:
        score += 12
    else:
        issues.append(ValidationIssue("Warning", "Sprint Readiness", "Story does not clearly follow user-value wording.", "Use As a / I want / So that or explain user value explicitly."))
    if criteria:
        score += 20
    if len(criteria) >= 2:
        score += 10
    if len(description.split()) <= 70:
        score += 10
    else:
        issues.append(ValidationIssue("Info", "Sprint Readiness", "Artifact may be too large for sprint-ready review.", "Split large scope into smaller artifacts if needed."))
    return min(score, 100), issues

