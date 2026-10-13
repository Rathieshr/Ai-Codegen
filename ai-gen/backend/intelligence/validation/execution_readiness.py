from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import names, string_list


def score_execution_readiness(planning_context: dict[str, Any], artifact: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    modules = names(planning_context.get("selectedModules"))
    flows = names(planning_context.get("selectedFlows"))
    dependencies = names(planning_context.get("selectedDependencies"))
    criteria = string_list(artifact.get("acceptanceCriteria") or artifact.get("acceptance_criteria"))
    score = 28 + min(len(modules), 3) * 12 + min(len(flows), 3) * 10 + min(len(dependencies), 2) * 8 + min(len(criteria), 3) * 6
    issues: list[ValidationIssue] = []
    if not modules or not flows:
        issues.append(ValidationIssue("Warning", "Execution Readiness", "Artifact lacks enough module or flow context for immediate execution.", "Add selected modules and flows or rebuild PlanningContext."))
    if not criteria:
        issues.append(ValidationIssue("Error", "Execution Readiness", "Artifact cannot be executed without acceptance criteria.", "Add acceptance criteria before creating execution packages."))
    return min(score, 100), issues

