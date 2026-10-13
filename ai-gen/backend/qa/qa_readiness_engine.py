"""QA readiness scoring."""

from __future__ import annotations

from typing import Any


class QAReadinessEngine:
    def calculate(
        self,
        coverage: dict[str, Any],
        tests: dict[str, Any],
        regression: dict[str, Any],
        risks: dict[str, Any],
        gaps: dict[str, Any],
        implementation_validation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validation = implementation_validation or {}
        acceptance_score = int(coverage.get("coveragePercent") or 0)
        test_score = _test_score(tests)
        repository_score = 90 if regression.get("potentialRegressionAreas") else 60
        validation_score = int(validation.get("testCoverageScore") or validation.get("standardsComplianceScore") or 80)
        regression_score = {"Low": 95, "Medium": 80, "High": 60, "Critical": 35}.get(risks.get("highestRisk"), 75)
        overall = int(round((acceptance_score * 0.3) + (test_score * 0.25) + (repository_score * 0.15) + (validation_score * 0.15) + (regression_score * 0.15)))
        blocking = bool(gaps.get("untestedAcceptanceCriteria")) or risks.get("highestRisk") == "Critical"
        status = "Blocked" if blocking or overall < 60 else "Needs Review" if overall < 85 or risks.get("highestRisk") == "High" else "Ready"
        return {
            "acceptanceCoverage": acceptance_score,
            "testCompleteness": test_score,
            "repositoryCoverage": repository_score,
            "validationStatus": validation.get("status") or "Not Run",
            "regressionRisk": risks.get("highestRisk") or "Medium",
            "overallReadiness": overall,
            "status": status,
            "blockers": _blockers(gaps, risks),
        }


def _test_score(tests: dict[str, Any]) -> int:
    categories = set(tests.get("categories") or [])
    required = {"Functional", "Negative", "Permission", "Regression"}
    return int(round((len(categories & required) / len(required)) * 100)) if required else 0


def _blockers(gaps: dict[str, Any], risks: dict[str, Any]) -> list[str]:
    blockers = []
    if gaps.get("untestedAcceptanceCriteria"):
        blockers.append("Untested acceptance criteria remain.")
    if gaps.get("missingPermissionOrSecurity"):
        blockers.append("Permission or security coverage is missing.")
    if risks.get("highestRisk") == "Critical":
        blockers.append("Critical QA risk must be resolved.")
    return blockers
