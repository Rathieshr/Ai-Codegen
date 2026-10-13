from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import artifact_text, names, score_from_overlap


def validate_coverage(planning_context: dict[str, Any], artifact: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    selected = " ".join([
        " ".join(names(planning_context.get("selectedCapabilities"))),
        " ".join(names(planning_context.get("selectedModules"))),
        " ".join(names(planning_context.get("selectedFlows"))),
        str(planning_context.get("expectedOutcome") or ""),
    ])
    score = score_from_overlap(artifact_text(artifact), selected, base=40)
    issues: list[ValidationIssue] = []
    if score < 55:
        issues.append(ValidationIssue("Warning", "Coverage", "Artifact does not cover enough selected PlanningContext evidence.", "Reference selected capability, module, flow, or expected outcome more clearly."))
    return score, issues

