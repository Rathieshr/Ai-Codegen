"""QA risk matrix."""

from __future__ import annotations

from typing import Any


class RiskIntelligenceEngine:
    def calculate(
        self,
        execution_package: dict[str, Any] | None,
        coverage: dict[str, Any],
        regression: dict[str, Any],
        gaps: dict[str, Any],
        implementation_validation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        package = execution_package or {}
        validation = implementation_validation or {}
        readiness = package.get("readiness") if isinstance(package.get("readiness"), dict) else {}
        risks = [
            _risk("Implementation Risk", _score_level(100 - int(validation.get("acceptanceCoverageScore") or coverage.get("coveragePercent") or 0)), "Acceptance coverage and implementation validation drive implementation risk."),
            _risk("Integration Risk", "High" if regression.get("affectedServices") or regression.get("affectedAPIs") else "Medium", "Affected services/APIs require integration verification."),
            _risk("Security Risk", "High" if gaps.get("missingPermissionOrSecurity") else "Low", "Permission and security tests must cover protected paths."),
            _risk("Regression Risk", regression.get("regressionPriority") or "Medium", "Regression priority is based on affected modules, flows, and changed files."),
            _risk("Repository Risk", "Medium" if not package.get("repositoryContext", {}).get("relevantFiles") else "Low", "Repository file ranking confidence affects QA certainty."),
            _risk("Dependency Risk", "High" if len(regression.get("potentialRegressionAreas") or []) > 5 else "Medium" if regression.get("potentialRegressionAreas") else "Low", "More impacted areas increase dependency risk."),
        ]
        if readiness.get("status") == "Blocked":
            risks.append(_risk("Execution Readiness Risk", "Critical", "Execution Package is blocked."))
        return {
            "risks": risks,
            "highestRisk": _highest(risks),
            "mitigations": [risk["mitigation"] for risk in risks if risk["level"] in {"High", "Critical"}],
        }


def _risk(name: str, level: str, reason: str) -> dict[str, str]:
    return {
        "name": name,
        "level": level if level in {"Low", "Medium", "High", "Critical"} else "Medium",
        "reason": reason,
        "mitigation": f"Address {name.lower()} before release." if level in {"High", "Critical"} else f"Monitor {name.lower()} during QA.",
    }


def _score_level(score: int) -> str:
    if score >= 70:
        return "Critical"
    if score >= 45:
        return "High"
    if score >= 20:
        return "Medium"
    return "Low"


def _highest(risks: list[dict[str, str]]) -> str:
    order = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
    return max((risk["level"] for risk in risks), key=lambda level: order.get(level, 1), default="Low")
