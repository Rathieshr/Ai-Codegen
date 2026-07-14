"""Deterministic rules for deciding whether Validation Intelligence should run."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import stable_hash


CHANGE_FIELDS = {
    "API": "apiChanges",
    "Module": "moduleChanges",
    "Service": "serviceChanges",
    "Dependency": "dependencyChanges",
    "Architecture": "architectureChanges",
    "Test": "testChanges",
    "Security": "securityChanges",
    "Configuration": "configurationChanges",
    "Database": "databaseChanges",
    "Documentation": "documentationChanges",
    "Refactoring": "refactoringChanges",
    "BreakingChange": "breakingChanges",
}

ALWAYS_VALIDATE = {"API", "Module", "Service", "Dependency", "Architecture", "Test", "Security", "Database", "Refactoring", "BreakingChange"}
SENSITIVE_CONFIG_TERMS = {"auth", "authorization", "connection", "credential", "database", "permission", "production", "secret", "security", "token"}


class ValidationTriggerEngine:
    def decide(
        self,
        engineering_diff: dict[str, Any],
        execution_result: dict[str, Any],
        execution_manifest: dict[str, Any],
        *,
        manual_override: Any = None,
        policy: dict[str, Any] | None = None,
        governance_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _validate_inputs(engineering_diff, execution_result, execution_manifest)
        policy = policy if isinstance(policy, dict) else {}
        governance_result = governance_result if isinstance(governance_result, dict) else {}
        override = _normalize_override(manual_override)
        change_counts = {name: _change_count(engineering_diff.get(field)) for name, field in CHANGE_FIELDS.items()}
        graph_count = _graph_change_count(engineering_diff.get("dependencyGraphChanges"))
        comments_only = _comments_only(engineering_diff, execution_result, change_counts, graph_count)
        rules: list[dict[str, Any]] = []

        policy_blockers = _policy_blockers(policy, governance_result)
        if policy_blockers:
            decision = "Blocked"
            reason = "; ".join(policy_blockers)
            confidence = 0.99
            _rule(rules, "policy_block", 1000, True, decision, reason)
        elif override["decision"] == "Skipped" and policy.get("allowManualSkip") is False:
            decision = "Blocked"
            reason = "Policy does not allow validation to be skipped manually."
            confidence = 0.99
            _rule(rules, "policy_manual_skip_prohibited", 990, True, decision, reason)
        elif _policy_requires_validation(policy, governance_result, change_counts, engineering_diff):
            decision = "Required"
            reason = "Validation is required by the active engineering policy."
            confidence = 0.98
            _rule(rules, "policy_validation_required", 980, True, decision, reason)
        elif override["decision"]:
            decision = override["decision"]
            reason = override["reason"] or f"Validation decision was manually overridden to {decision}."
            confidence = 1.0
            _rule(rules, "manual_override", 900, True, decision, reason)
        elif str(execution_result.get("status") or "").casefold() in {"failed", "cancelled", "blocked"}:
            decision = "Blocked"
            reason = f"Execution Result status is {execution_result.get('status')}; validation cannot start from an incomplete result."
            confidence = 0.99
            _rule(rules, "execution_result_not_validatable", 850, True, decision, reason)
        else:
            decision, reason, confidence = self._engineering_decision(
                engineering_diff,
                execution_manifest,
                change_counts,
                graph_count,
                comments_only,
                rules,
            )

        core = {
            "engineeringDiffId": engineering_diff.get("diffId"),
            "executionResultId": execution_result.get("resultId") or execution_result.get("interpretationId"),
            "executionManifestId": execution_manifest.get("manifestId"),
            "decision": decision,
            "override": override,
            "policy": policy,
        }
        event_type = {"Required": "ValidationRequested", "Skipped": "ValidationSkipped", "Blocked": "ValidationBlocked"}[decision]
        return {
            "decisionId": f"validation_trigger_{stable_hash(core)[:12]}",
            "decisionVersion": "5.4",
            "decision": decision,
            "validationRequired": decision == "Required",
            "reason": reason,
            "confidence": round(confidence, 2),
            "rulesUsed": rules,
            "eventType": event_type,
            "engineeringDiffId": str(engineering_diff.get("diffId") or ""),
            "executionResultId": str(execution_result.get("resultId") or execution_result.get("interpretationId") or ""),
            "executionManifestId": str(execution_manifest.get("manifestId") or ""),
            "sessionId": str(execution_result.get("sessionId") or engineering_diff.get("sessionId") or ""),
            "correlationId": str(execution_result.get("correlationId") or (execution_result.get("diagnostics") or {}).get("correlationId") or ""),
            "manualOverride": override,
            "policy": {
                "applied": bool(policy or governance_result),
                "input": deepcopy(policy),
                "governanceStatus": str(governance_result.get("status") or "NotEvaluated"),
                "governanceViolations": deepcopy(governance_result.get("violations") or []),
            },
            "changeSummary": {"changeTypes": change_counts, "dependencyGraphChanges": graph_count, "commentsOnly": comments_only},
            "diagnostics": {
                "rulePrecedence": [
                    "policy_block",
                    "policy_required",
                    "manual_override",
                    "invalid_execution_result",
                    "critical_or_high_impact",
                    "hard_engineering_change",
                    "configuration_conditional",
                    "documentation_or_comments_only",
                    "default",
                ],
                "validationInvoked": False,
                "providerCalls": 0,
                "deterministic": True,
            },
            "decidedAt": datetime.now(timezone.utc).isoformat(),
        }

    def _engineering_decision(
        self,
        engineering_diff: dict[str, Any],
        manifest: dict[str, Any],
        counts: dict[str, int],
        graph_count: int,
        comments_only: bool,
        rules: list[dict[str, Any]],
    ) -> tuple[str, str, float]:
        impact = str((engineering_diff.get("impact") or {}).get("level") or "Low")
        if impact in {"Critical", "High"}:
            reason = f"Engineering Diff impact is {impact}."
            _rule(rules, "high_impact_requires_validation", 800, True, "Required", reason)
            return "Required", reason, 0.98

        required_types = sorted(name for name in ALWAYS_VALIDATE if counts.get(name, 0))
        if graph_count:
            required_types.append("DependencyGraph")
        if required_types:
            reason = f"Validation is required for: {', '.join(required_types)}."
            _rule(rules, "engineering_change_requires_validation", 700, True, "Required", reason)
            return "Required", reason, 0.96

        if counts.get("Configuration"):
            sensitive = _sensitive_configuration(engineering_diff, manifest)
            if sensitive:
                reason = "Configuration changes affect sensitive or explicitly validated engineering settings."
                _rule(rules, "configuration_conditional", 600, True, "Required", reason)
                return "Required", reason, 0.92
            reason = "Configuration-only changes are non-sensitive and no manifest validation requirement matched."
            _rule(rules, "configuration_conditional", 600, True, "Skipped", reason)
            return "Skipped", reason, 0.78

        non_documentation = sum(count for name, count in counts.items() if name != "Documentation")
        if counts.get("Documentation") and not non_documentation and not graph_count:
            reason = "Only documentation changed."
            _rule(rules, "documentation_only_skip", 500, True, "Skipped", reason)
            return "Skipped", reason, 0.98
        if comments_only:
            reason = "Only comments changed."
            _rule(rules, "comments_only_skip", 500, True, "Skipped", reason)
            return "Skipped", reason, 0.94
        if sum(counts.values()) == 0 and not graph_count:
            reason = "No semantic engineering changes were detected."
            _rule(rules, "no_semantic_change_skip", 400, True, "Skipped", reason)
            return "Skipped", reason, 0.9

        reason = "Semantic engineering changes remain after rule evaluation."
        _rule(rules, "default_validate", 100, True, "Required", reason)
        return "Required", reason, 0.72


def _validate_inputs(diff: Any, result: Any, manifest: Any) -> None:
    if not isinstance(diff, dict) or not str(diff.get("diffId") or ""):
        raise ValueError("engineeringDiff with diffId is required.")
    if not isinstance(result, dict):
        raise ValueError("executionResult is required.")
    if not isinstance(manifest, dict) or not str(manifest.get("manifestId") or ""):
        raise ValueError("executionManifest with manifestId is required.")


def _change_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    return sum(len(value.get(bucket) or []) for bucket in ("added", "modified", "removed", "moved"))


def _graph_change_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    return sum(len(item) for item in value.values() if isinstance(item, list))


def _normalize_override(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        raw = value.get("decision") or value.get("action") or value.get("value")
        reason = str(value.get("reason") or "")
        actor = str(value.get("actor") or value.get("requestedBy") or "")
    else:
        raw, reason, actor = value, "", ""
    normalized = str(raw or "").strip().casefold().replace("_", "")
    decision = {
        "require": "Required", "required": "Required", "run": "Required", "forcevalidation": "Required",
        "skip": "Skipped", "skipped": "Skipped", "forceskip": "Skipped",
        "block": "Blocked", "blocked": "Blocked",
    }.get(normalized, "")
    if raw and not decision:
        raise ValueError("manualOverride must be require, skip, or block.")
    return {"applied": bool(decision), "decision": decision, "reason": reason, "actor": actor}


def _policy_blockers(policy: dict[str, Any], governance: dict[str, Any]) -> list[str]:
    reasons = [str(value) for value in policy.get("blockedReasons") or [] if str(value)]
    if policy.get("blocked") or policy.get("validationBlocked"):
        reasons.append(str(policy.get("reason") or "Validation is blocked by policy."))
    for violation in governance.get("violations") or []:
        if isinstance(violation, dict) and str(violation.get("severity") or "") in {"High", "Critical"}:
            reasons.append(str(violation.get("message") or "Governance policy blocked validation."))
    return list(dict.fromkeys(reasons))


def _policy_requires_validation(policy: dict[str, Any], governance: dict[str, Any], counts: dict[str, int], diff: dict[str, Any]) -> bool:
    if policy.get("validationRequired") is True:
        return True
    required_types = {str(value).casefold() for value in policy.get("requiredChangeTypes") or []}
    if any(count and name.casefold() in required_types for name, count in counts.items()):
        return True
    required_levels = {str(value).casefold() for value in policy.get("requiredImpactLevels") or []}
    impact = str((diff.get("impact") or {}).get("level") or "").casefold()
    return bool(impact and impact in required_levels) or governance.get("validationRequired") is True


def _comments_only(diff: dict[str, Any], result: dict[str, Any], counts: dict[str, int], graph_count: int) -> bool:
    if sum(counts.values()) or graph_count:
        return False
    if diff.get("commentsOnly") is True:
        return True
    artifacts = result.get("engineeringArtifacts") or result.get("artifacts") or []
    if not isinstance(artifacts, list) or not artifacts:
        return False
    return all(str(item.get("type") or item.get("artifactType") or "").casefold() in {"comment", "comments"} for item in artifacts if isinstance(item, dict))


def _sensitive_configuration(diff: dict[str, Any], manifest: dict[str, Any]) -> bool:
    changes = diff.get("configurationChanges") if isinstance(diff.get("configurationChanges"), dict) else {}
    text_parts: list[str] = []
    for bucket in ("added", "modified", "removed", "moved"):
        for change in changes.get(bucket) or []:
            text_parts.append(str(change))
    validation = manifest.get("validationGuidance") if isinstance(manifest.get("validationGuidance"), dict) else {}
    if validation.get("required") or validation.get("validationRequired"):
        return True
    text_parts.extend(str(value) for value in manifest.get("engineeringStandards") or [])
    text_parts.extend(str(value) for value in manifest.get("risks") or [])
    text = " ".join(text_parts).casefold()
    return any(term in text for term in SENSITIVE_CONFIG_TERMS)


def _rule(rules: list[dict[str, Any]], rule_id: str, priority: int, matched: bool, outcome: str, reason: str) -> None:
    rules.append({"ruleId": rule_id, "priority": priority, "matched": matched, "outcome": outcome, "reason": reason})
