from __future__ import annotations

import time
from typing import Any

from .acceptance_criteria_validator import validate_acceptance_criteria
from .business_validator import validate_business_alignment
from .capability_validator import validate_capability_alignment
from .coverage_validator import validate_coverage
from .duplicate_validator import validate_duplicates
from .engineering_readiness import score_engineering_readiness
from .execution_readiness import score_execution_readiness
from .knowledge_validator import validate_knowledge_alignment
from .repository_validator import validate_repository_alignment
from .sprint_readiness import score_sprint_readiness
from .validation_report import ValidationIssue, ValidationReport
from .validation_utils import clamp


class ValidationEngine:
    def validate_artifact(
        self,
        planning_context: dict[str, Any],
        artifact: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        options = options or {}
        _validate_inputs(planning_context, artifact)
        existing_siblings = _existing_siblings(planning_context, options)

        business_score, business_issues = validate_business_alignment(planning_context, artifact)
        capability_score, capability_issues = validate_capability_alignment(planning_context, artifact)
        repository_score, repository_issues = validate_repository_alignment(planning_context, artifact, options)
        knowledge_score, knowledge_issues = validate_knowledge_alignment(planning_context, artifact, options)
        ac_score, ac_issues = validate_acceptance_criteria(artifact)
        duplicate_risk, duplicate_issues = validate_duplicates(artifact, existing_siblings)
        coverage_score, coverage_issues = validate_coverage(planning_context, artifact)
        engineering_score, engineering_issues = score_engineering_readiness(planning_context, artifact)
        sprint_score, sprint_issues = score_sprint_readiness(artifact)
        execution_score, execution_issues = score_execution_readiness(planning_context, artifact)

        issues = [
            *business_issues,
            *capability_issues,
            *repository_issues,
            *knowledge_issues,
            *ac_issues,
            *duplicate_issues,
            *coverage_issues,
            *engineering_issues,
            *sprint_issues,
            *execution_issues,
        ]
        overall = clamp(
            (
                business_score
                + capability_score
                + repository_score
                + knowledge_score
                + ac_score
                + coverage_score
                + engineering_score
                + sprint_score
                + execution_score
            )
            / 9
            - duplicate_risk * 0.18
        )
        status = _status(overall, issues)
        recommendations = _recommendations(issues, status)
        confidence = clamp((overall + int(float(planning_context.get("confidence", 0.55) or 0.55) * 100)) / 2) / 100
        report = ValidationReport(
            validation_status=status,
            overall_score=overall,
            business_alignment=business_score,
            capability_alignment=capability_score,
            repository_alignment=repository_score,
            engineering_readiness=engineering_score,
            sprint_readiness=sprint_score,
            execution_readiness=execution_score,
            duplicate_risk=duplicate_risk,
            confidence=confidence,
            issues=issues,
            recommendations=recommendations,
            diagnostics={
                "validationDurationMs": int((time.perf_counter() - started) * 1000),
                "knowledgeAlignment": knowledge_score,
                "acceptanceCriteriaScore": ac_score,
                "coverageScore": coverage_score,
                "detectedIssueCount": len(issues),
            },
        )
        return report.to_dict()


def validate_artifact(planning_context: dict[str, Any], artifact: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    return ValidationEngine().validate_artifact(planning_context, artifact, options)


def validateArtifact(planningContext: dict[str, Any], artifact: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    return validate_artifact(planningContext, artifact, options)


def _validate_inputs(planning_context: dict[str, Any], artifact: dict[str, Any]) -> None:
    if not isinstance(planning_context, dict):
        raise ValueError("PlanningContext must be a dictionary.")
    if not isinstance(artifact, dict):
        raise ValueError("Generated artifact must be a dictionary.")
    missing = [key for key in ["businessGoal", "userProblem", "expectedOutcome"] if key not in planning_context]
    if missing:
        raise ValueError(f"PlanningContext missing required field(s): {', '.join(missing)}")


def _existing_siblings(planning_context: dict[str, Any], options: dict[str, Any]) -> list[dict[str, Any]]:
    siblings = options.get("existing_siblings") or options.get("existingSiblings") or planning_context.get("existingChildren") or []
    return [item for item in siblings if isinstance(item, dict)] if isinstance(siblings, list) else []


def _status(overall: int, issues: list[ValidationIssue]) -> str:
    if any(issue.severity == "Error" for issue in issues) or overall < 55:
        return "Rejected"
    if any(issue.severity == "Warning" for issue in issues) or overall < 78:
        return "NeedsReview"
    return "Approved"


def _recommendations(issues: list[ValidationIssue], status: str) -> list[str]:
    output: list[str] = []
    for issue in issues:
        if issue.recommendation and issue.recommendation not in output:
            output.append(issue.recommendation)
    if not output and status == "Approved":
        output.append("Artifact is ready for human approval.")
    return output[:8]

