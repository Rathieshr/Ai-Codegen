from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import names


def score_engineering_readiness(planning_context: dict[str, Any], artifact: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    modules = names(planning_context.get("selectedModules"))
    flows = names(planning_context.get("selectedFlows"))
    dependencies = names(planning_context.get("selectedDependencies"))
    standards = names(planning_context.get("selectedStandards"))
    score = 35 + min(len(modules), 3) * 12 + min(len(flows), 3) * 10 + min(len(dependencies), 2) * 8 + min(len(standards), 2) * 7
    issues: list[ValidationIssue] = []
    if not modules:
        issues.append(ValidationIssue("Warning", "Engineering Readiness", "No repository modules selected.", "Rebuild PlanningContext with repository or knowledge module evidence."))
    if not flows:
        issues.append(ValidationIssue("Warning", "Engineering Readiness", "No flows selected.", "Add flow context before execution planning."))
    if not dependencies:
        issues.append(ValidationIssue("Info", "Engineering Readiness", "No dependencies selected.", "Confirm ownership and integration dependencies during review."))
    return min(score, 100), issues

