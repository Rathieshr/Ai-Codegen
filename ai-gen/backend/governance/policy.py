"""Configurable governance policy enforcement."""

from __future__ import annotations

from typing import Any

from .types import default_policy_config, normalize_policy, number


class PolicyEngine:
    def default_policies(self) -> list[dict[str, Any]]:
        config = default_policy_config()
        return [
            normalize_policy({
                "id": "planning-approval-required",
                "name": "Story approval before execution",
                "area": "Planning",
                "description": "Stories must be approved before execution starts.",
                "rules": {"story_requires_approval_before_execution": config["planning"]["story_requires_approval_before_execution"]},
            }),
            normalize_policy({
                "id": "execution-package-required",
                "name": "Execution Package required",
                "area": "Execution",
                "description": "Developer prompt generation requires an execution package.",
                "rules": {"execution_package_required": config["execution"]["execution_package_required"]},
            }),
            normalize_policy({
                "id": "qa-coverage-threshold",
                "name": "Acceptance coverage threshold",
                "area": "QA",
                "description": "QA readiness requires acceptance coverage above threshold.",
                "rules": {"acceptance_coverage_threshold": config["qa"]["acceptance_coverage_threshold"]},
            }),
            normalize_policy({
                "id": "release-gate",
                "name": "Release governance gate",
                "area": "Release",
                "description": "Release requires QA ready, validation passed, and PR review completed.",
                "rules": config["release"],
            }),
        ]

    def enforce(self, artifact: dict[str, Any], context: dict[str, Any], policies: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        active = [normalize_policy(policy) for policy in (policies or self.default_policies()) if policy.get("enabled", True)]
        violations: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for policy in active:
            for finding in self._evaluate_policy(policy, artifact, context):
                if finding["severity"] in {"Critical", "High"}:
                    violations.append(finding)
                else:
                    warnings.append(finding)
        compliant = not violations
        return {
            "compliant": compliant,
            "status": "Passed" if compliant else "Blocked",
            "policiesEvaluated": len(active),
            "violations": violations,
            "warnings": warnings,
        }

    def _evaluate_policy(self, policy: dict[str, Any], artifact: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        rules = policy.get("rules") if isinstance(policy.get("rules"), dict) else {}
        findings: list[dict[str, Any]] = []
        artifact_type = str(artifact.get("artifactType") or artifact.get("type") or "")
        approval_status = str(artifact.get("approvalStatus") or artifact.get("status") or context.get("approvalStatus") or "")
        if rules.get("story_requires_approval_before_execution") and artifact_type.lower() == "story" and approval_status.lower() not in {"approved", "locked"}:
            findings.append(self._finding(policy, "Story requires approval before execution.", "High"))
        if rules.get("execution_package_required") and context.get("operation") in {"Generate Developer Prompt", "Open Execution"} and not context.get("executionPackage"):
            findings.append(self._finding(policy, "Execution Package is required before prompt generation.", "High"))
        threshold = number(rules.get("acceptance_coverage_threshold"), -1)
        if threshold >= 0 and context.get("qa"):
            coverage = number(context.get("qa", {}).get("acceptanceCoverage") or context.get("qa", {}).get("coverage_score"), 0)
            if coverage < threshold:
                findings.append(self._finding(policy, f"Acceptance coverage {coverage:.0f}% is below required {threshold:.0f}%.", "High"))
        if rules.get("qa_ready_required") and context.get("release"):
            if str(context.get("qaStatus") or context.get("qa", {}).get("status") or "").lower() not in {"ready", "passed", "release ready"}:
                findings.append(self._finding(policy, "QA must be ready before release.", "Critical"))
        if rules.get("validation_passed_required") and context.get("release"):
            if str(context.get("validationStatus") or "").lower() not in {"passed", "approved"}:
                findings.append(self._finding(policy, "Implementation validation must pass before release.", "Critical"))
        if rules.get("pr_review_completed_required") and context.get("release"):
            if str(context.get("prReviewStatus") or "").lower() not in {"completed", "passed", "approved"}:
                findings.append(self._finding(policy, "PR review must be completed before release.", "High"))
        repository_threshold = number(rules.get("repository_confidence_threshold"), -1)
        if repository_threshold >= 0 and context.get("repositoryConfidence") is not None:
            confidence = number(context.get("repositoryConfidence"), 0)
            if confidence < repository_threshold:
                findings.append(self._finding(policy, f"Repository confidence {confidence:.0f}% is below required {repository_threshold:.0f}%.", "Medium"))
        return findings

    def _finding(self, policy: dict[str, Any], message: str, severity: str) -> dict[str, Any]:
        return {
            "policyId": policy["id"],
            "policy": policy["name"],
            "area": policy["area"],
            "severity": severity,
            "message": message,
        }
