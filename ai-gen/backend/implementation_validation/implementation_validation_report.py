"""Report assembly for Implementation Validation V1."""

from __future__ import annotations

from typing import Any

from .models import now_iso, stable_id


def build_report(
    *,
    execution_package: dict[str, Any],
    changed_files: list[dict[str, Any]],
    acceptance: dict[str, Any],
    scope: dict[str, Any],
    repository: dict[str, Any],
    standards: dict[str, Any],
    tests: dict[str, Any],
    build_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    violations = []
    for section in (acceptance, scope, repository, standards, tests):
        violations.extend(section.get("violations") or [])
    scores = {
        "acceptanceCoverageScore": int(acceptance.get("score") or 0),
        "scopeComplianceScore": int(scope.get("score") or 0),
        "repositoryAlignmentScore": int(repository.get("score") or 0),
        "standardsComplianceScore": int(standards.get("score") or 0),
        "testCoverageScore": int(tests.get("score") or 0),
    }
    risk_score = _risk_score(scores, violations, build_result or {})
    status = _status(scores, violations, build_result or {})
    recommendations = _recommendations(violations, scores, build_result or {})
    package_id = execution_package.get("packageId") or execution_package.get("package_id") or ""
    return {
        "reportId": stable_id("implval", {"package": package_id, "files": [file.get("path") for file in changed_files], "scores": scores}),
        "packageId": package_id,
        "taskId": execution_package.get("taskId"),
        "storyId": execution_package.get("storyId"),
        "status": status,
        **scores,
        "riskScore": risk_score,
        "changedFiles": repository.get("changedFiles") or [{"path": file.get("path"), "status": "needs review"} for file in changed_files],
        "acceptanceResults": acceptance.get("results") or [],
        "scopeCompliance": {"score": scores["scopeComplianceScore"], "touchedBlockedScope": scope.get("touchedBlockedScope") or []},
        "repositoryAlignment": {"score": scores["repositoryAlignmentScore"]},
        "standards": standards.get("checks") or [],
        "tests": tests.get("results") or [],
        "violations": violations,
        "recommendations": recommendations,
        "buildResult": build_result or {},
        "generatedAt": now_iso(),
    }


def _status(scores: dict[str, int], violations: list[dict[str, Any]], build_result: dict[str, Any]) -> str:
    if any(v.get("severity") == "critical" for v in violations):
        return "Failed"
    if build_result and str(build_result.get("status") or "").casefold() in {"failed", "failure", "error"}:
        return "Failed"
    if min(scores.values()) >= 80 and not violations:
        return "Passed"
    return "NeedsReview"


def _risk_score(scores: dict[str, int], violations: list[dict[str, Any]], build_result: dict[str, Any]) -> int:
    severity_penalty = sum(25 if v.get("severity") == "critical" else 12 if v.get("severity") == "major" else 5 for v in violations)
    score_gap = sum(max(0, 80 - value) for value in scores.values()) // max(1, len(scores))
    build_penalty = 20 if str(build_result.get("status") or "").casefold() in {"failed", "failure", "error"} else 0
    return min(100, severity_penalty + score_gap + build_penalty)


def _recommendations(violations: list[dict[str, Any]], scores: dict[str, int], build_result: dict[str, Any]) -> list[str]:
    recs = [item.get("recommendation") for item in violations if item.get("recommendation")]
    if scores["acceptanceCoverageScore"] < 80:
        recs.append("Map each acceptance criterion to implementation evidence and validation evidence.")
    if scores["testCoverageScore"] < 80:
        recs.append("Add the missing unit, integration, permission, negative, or regression tests from the Execution Package.")
    if scores["repositoryAlignmentScore"] < 80:
        recs.append("Keep changes inside repository evidence from the Execution Package or update the package before approval.")
    if build_result and str(build_result.get("status") or "").casefold() in {"failed", "failure", "error"}:
        recs.append("Fix the failing build result before approving implementation alignment.")
    unique = []
    seen = set()
    for rec in recs:
        if rec and rec not in seen:
            seen.add(rec)
            unique.append(rec)
    return unique
