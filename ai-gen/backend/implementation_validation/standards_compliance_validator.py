"""Engineering standards compliance validation."""

from __future__ import annotations

from typing import Any

from .models import clean, lower_blob, score_from_results, violation


class StandardsComplianceValidator:
    def validate(self, execution_package: dict[str, Any], changed_files: list[dict[str, Any]]) -> dict[str, Any]:
        rules = execution_package.get("engineeringRules") if isinstance(execution_package.get("engineeringRules"), list) else []
        blob = lower_blob(*[file.get("path") for file in changed_files], *[file.get("diff") for file in changed_files])
        checks = []
        for name, keywords in _required_checks(rules).items():
            matched = [keyword for keyword in keywords if keyword in blob]
            status = "met" if matched else ("not verifiable" if not blob.strip() else "missing")
            checks.append({"standard": name, "status": status, "evidence": matched})
        violations = [
            violation(
                rule="engineering_standard",
                severity="major" if check["status"] == "missing" else "minor",
                message=f"{check['standard']} is {check['status']}.",
                recommendation="Add implementation evidence or tests for this standard.",
            )
            for check in checks
            if check["status"] in {"missing", "not verifiable"}
        ]
        return {"score": score_from_results(checks, {"met"}), "checks": checks, "violations": violations}


def _required_checks(rules: list[Any]) -> dict[str, list[str]]:
    text = " ".join(clean(rule).casefold() for rule in rules)
    checks: dict[str, list[str]] = {}
    if "logging" in text:
        checks["structured logging"] = ["logger", "logging", "log."]
    if "validation" in text or "input" in text:
        checks["input validation"] = ["validate", "validation", "required", "invalid"]
    if "auth" in text or "role" in text or "permission" in text:
        checks["authorization"] = ["authorize", "authorization", "permission", "role", "forbid"]
    if "audit" in text:
        checks["audit logging"] = ["audit", "trail", "history"]
    if "secure" in text or "security" in text:
        checks["secure communication"] = ["https", "token", "secret", "secure"]
    if "test" in text:
        checks["tests"] = ["test", "spec", "assert"]
    if not checks:
        checks["tests"] = ["test", "spec", "assert"]
    return checks
