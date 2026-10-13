"""Deterministic QA activity selection from validated engineering outcomes."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import stable_hash


ACTIVITY_ORDER = (
    "Unit Tests",
    "Integration Tests",
    "Regression Tests",
    "Permission Tests",
    "Performance Tests",
    "Security Tests",
    "Smoke Tests",
    "UI Tests",
)

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

UI_TERMS = (
    ".css",
    ".dart",
    ".html",
    ".jsx",
    ".scss",
    ".tsx",
    ".xaml",
    "component",
    "frontend",
    "screen",
    "ui change",
    "user interface",
    "viewmodel",
    "widget",
)
SECURITY_TERMS = ("auth", "authorization", "credential", "permission", "role", "secret", "security", "token")
PERFORMANCE_TERMS = ("latency", "load", "performance", "response time", "scalability", "throughput")


class QATriggerEngine:
    def plan(self, engineering_diff: dict[str, Any], validation_result: dict[str, Any], execution_manifest: dict[str, Any]) -> dict[str, Any]:
        _validate_inputs(engineering_diff, validation_result, execution_manifest)
        counts = {name: _change_count(engineering_diff.get(field)) for name, field in CHANGE_FIELDS.items()}
        graph_count = _graph_change_count(engineering_diff.get("dependencyGraphChanges"))
        ui_change = _has_ui_change(engineering_diff, execution_manifest)
        comments_only = bool(engineering_diff.get("commentsOnly"))
        validation_status = str(validation_result.get("status") or validation_result.get("validationStatus") or "Unknown")
        activities: dict[str, dict[str, Any]] = {}
        rules: list[dict[str, Any]] = []

        if validation_status.casefold() in {"blocked", "failed", "rejected", "cancelled"}:
            decision = "Skipped"
            reason = f"QA is skipped because Validation Result is {validation_status}."
            confidence = 0.99
            _rule(rules, "validation_not_ready", 1000, reason)
        elif _documentation_only(counts, graph_count, ui_change):
            decision = "Skipped"
            reason = "Only documentation changed; no engineering QA activity is required."
            confidence = 0.98
            _rule(rules, "documentation_only_skip", 900, reason)
        elif comments_only and not sum(counts.values()) and not graph_count and not ui_change:
            decision = "Skipped"
            reason = "Only comments changed; no engineering QA activity is required."
            confidence = 0.96
            _rule(rules, "comments_only_skip", 900, reason)
        elif not sum(counts.values()) and not graph_count and not ui_change:
            decision = "Skipped"
            reason = "No semantic engineering changes were detected."
            confidence = 0.9
            _rule(rules, "no_change_skip", 800, reason)
        else:
            decision = "Requested"
            self._select_activities(activities, rules, counts, graph_count, ui_change, engineering_diff, validation_result, execution_manifest)
            reason = _request_reason(activities, counts, ui_change)
            confidence = _confidence(engineering_diff, validation_result, activities)

        required = [activities[name] for name in ACTIVITY_ORDER if name in activities]
        flags = {f"need{_flag_name(name)}": name in activities for name in ACTIVITY_ORDER}
        core = {
            "engineeringDiffId": engineering_diff.get("diffId"),
            "validationResultId": validation_result.get("reportId") or validation_result.get("validationId"),
            "executionManifestId": execution_manifest.get("manifestId"),
            "decision": decision,
            "activities": [item["type"] for item in required],
        }
        return {
            "planId": f"qa_execution_plan_{stable_hash(core)[:12]}",
            "planVersion": "5.5",
            "decision": decision,
            "qaRequired": decision == "Requested",
            **flags,
            "requiredActivities": required,
            "reason": reason,
            "confidence": round(confidence, 2),
            "rulesUsed": rules,
            "eventType": "QARequested" if decision == "Requested" else "QASkipped",
            "engineeringDiffId": str(engineering_diff.get("diffId") or ""),
            "validationResultId": str(validation_result.get("reportId") or validation_result.get("validationId") or ""),
            "executionManifestId": str(execution_manifest.get("manifestId") or ""),
            "sessionId": str(engineering_diff.get("sessionId") or validation_result.get("sessionId") or ""),
            "correlationId": str(validation_result.get("correlationId") or (validation_result.get("diagnostics") or {}).get("correlationId") or ""),
            "changeSummary": {"changeTypes": counts, "dependencyGraphChanges": graph_count, "uiChangeDetected": ui_change},
            "validationSummary": {
                "status": validation_status,
                "acceptanceCoverageScore": validation_result.get("acceptanceCoverageScore"),
                "testCoverageScore": validation_result.get("testCoverageScore"),
                "violations": deepcopy(validation_result.get("violations") or []),
            },
            "diagnostics": {
                "qaInvoked": False,
                "testsGenerated": False,
                "providerCalls": 0,
                "deterministic": True,
                "activityOrder": list(ACTIVITY_ORDER),
            },
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    def _select_activities(
        self,
        activities: dict[str, dict[str, Any]],
        rules: list[dict[str, Any]],
        counts: dict[str, int],
        graph_count: int,
        ui_change: bool,
        diff: dict[str, Any],
        validation: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        if counts["API"]:
            _add(activities, "Unit Tests", "High", "API behavior changed.", "Engineering Diff API changes")
            _add(activities, "Integration Tests", "High", "API contracts must be verified across service boundaries.", "Engineering Diff API changes")
            _add(activities, "Regression Tests", "High", "Existing API consumers may be affected.", "Engineering Diff API changes")
            _add(activities, "Permission Tests", "High", "API authorization boundaries must remain valid.", "Engineering Diff API changes")
            _add(activities, "Smoke Tests", "High", "Changed endpoints require a basic availability check.", "Engineering Diff API changes")
            _rule(rules, "api_change", 800, "API changes require unit, integration, regression, permission, and smoke tests.")
        if counts["Database"]:
            _add(activities, "Integration Tests", "Critical", "Database behavior must be verified with application integration.", "Engineering Diff database changes")
            _add(activities, "Regression Tests", "High", "Schema or migration changes may affect existing data paths.", "Engineering Diff database changes")
            _add(activities, "Performance Tests", "High", "Database changes may alter query or migration performance.", "Engineering Diff database changes")
            _add(activities, "Smoke Tests", "High", "Database startup and migration health must be verified.", "Engineering Diff database changes")
            _rule(rules, "database_change", 800, "Database changes require integration, regression, performance, and smoke tests.")
        if ui_change:
            _add(activities, "Unit Tests", "Medium", "Changed UI behavior requires component or view-model verification.", "UI evidence")
            _add(activities, "UI Tests", "High", "User-visible behavior changed.", "UI evidence")
            _add(activities, "Regression Tests", "High", "Existing user journeys may be affected.", "UI evidence")
            _add(activities, "Smoke Tests", "Medium", "The affected screen or component must open successfully.", "UI evidence")
            _rule(rules, "ui_change", 800, "UI changes require UI, unit, regression, and smoke tests.")
        if counts["Configuration"]:
            _add(activities, "Smoke Tests", "High", "Configuration must load successfully in the target environment.", "Engineering Diff configuration changes")
            _add(activities, "Regression Tests", "Medium", "Configuration changes can alter existing runtime behavior.", "Engineering Diff configuration changes")
            if _contains_terms(diff, manifest, SECURITY_TERMS):
                _add(activities, "Security Tests", "Critical", "Sensitive configuration changed.", "Security-sensitive configuration evidence")
                _add(activities, "Permission Tests", "High", "Access configuration changed.", "Security-sensitive configuration evidence")
            _rule(rules, "configuration_change", 700, "Configuration changes require smoke and regression coverage, with security coverage when sensitive.")
        if counts["Architecture"]:
            _add(activities, "Integration Tests", "Critical", "Architecture boundaries or communication paths changed.", "Engineering Diff architecture changes")
            _add(activities, "Regression Tests", "High", "Architecture changes can affect multiple existing paths.", "Engineering Diff architecture changes")
            _add(activities, "Performance Tests", "Medium", "Architecture changes may alter latency or throughput.", "Engineering Diff architecture changes")
            _add(activities, "Smoke Tests", "High", "The revised architecture must start and serve its primary path.", "Engineering Diff architecture changes")
            _rule(rules, "architecture_change", 800, "Architecture changes require integration, regression, performance, and smoke tests.")
        if counts["Security"]:
            _add(activities, "Security Tests", "Critical", "Security behavior changed.", "Engineering Diff security changes")
            _add(activities, "Permission Tests", "Critical", "Authorization behavior must be verified.", "Engineering Diff security changes")
            _add(activities, "Regression Tests", "High", "Existing protected paths may be affected.", "Engineering Diff security changes")
        if counts["Module"] or counts["Service"] or counts["Refactoring"]:
            _add(activities, "Unit Tests", "High", "Implementation behavior changed within modules or services.", "Module, service, or refactoring changes")
            _add(activities, "Integration Tests", "Medium", "Module and service boundaries must remain compatible.", "Module, service, or refactoring changes")
            _add(activities, "Regression Tests", "High", "Existing behavior must remain stable.", "Module, service, or refactoring changes")
        if counts["Dependency"] or graph_count:
            _add(activities, "Integration Tests", "High", "Dependency relationships changed.", "Dependency graph changes")
            _add(activities, "Regression Tests", "High", "Dependent behavior may regress.", "Dependency graph changes")
            _add(activities, "Smoke Tests", "Medium", "Changed dependencies must resolve at runtime.", "Dependency graph changes")
        if counts["Test"]:
            _add(activities, "Regression Tests", "Medium", "The changed test suite must be rerun.", "Engineering Diff test changes")
        if counts["BreakingChange"]:
            for activity in ("Unit Tests", "Integration Tests", "Regression Tests", "Smoke Tests"):
                _add(activities, activity, "Critical", "A breaking change was reported.", "Execution Result breaking-change evidence")
        evidence_text = _validation_text(validation)
        if any(term in evidence_text for term in SECURITY_TERMS):
            _add(activities, "Security Tests", "High", "Validation reported a security-related gap.", "Validation Result")
            _add(activities, "Permission Tests", "High", "Validation reported an access-related gap.", "Validation Result")
        if any(term in evidence_text for term in PERFORMANCE_TERMS):
            _add(activities, "Performance Tests", "High", "Validation reported a performance-related gap.", "Validation Result")
        if not activities:
            _add(activities, "Unit Tests", "Medium", "A semantic implementation change requires focused verification.", "Engineering Diff")
            _add(activities, "Regression Tests", "Medium", "Existing behavior should be protected.", "Engineering Diff")
            _rule(rules, "default_engineering_change", 100, "Unclassified engineering changes require unit and regression tests.")


def _validate_inputs(diff: Any, validation: Any, manifest: Any) -> None:
    if not isinstance(diff, dict) or not str(diff.get("diffId") or ""):
        raise ValueError("engineeringDiff with diffId is required.")
    if not isinstance(validation, dict):
        raise ValueError("validationResult is required.")
    if not isinstance(manifest, dict) or not str(manifest.get("manifestId") or ""):
        raise ValueError("executionManifest with manifestId is required.")


def _change_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    return sum(len(value.get(bucket) or []) for bucket in ("added", "modified", "removed", "moved"))


def _graph_change_count(value: Any) -> int:
    return sum(len(item) for item in value.values() if isinstance(item, list)) if isinstance(value, dict) else 0


def _documentation_only(counts: dict[str, int], graph_count: int, ui_change: bool) -> bool:
    return bool(counts["Documentation"] and sum(value for key, value in counts.items() if key != "Documentation") == 0 and not graph_count and not ui_change)


def _has_ui_change(diff: dict[str, Any], manifest: dict[str, Any]) -> bool:
    if _change_count(diff.get("uiChanges")):
        return True
    text = _evidence_text(diff, manifest)
    return any(term in text for term in UI_TERMS)


def _evidence_text(diff: dict[str, Any], manifest: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in (*CHANGE_FIELDS.values(), "uiChanges"):
        value = diff.get(field)
        if isinstance(value, dict):
            for bucket in ("added", "modified", "removed", "moved"):
                parts.extend(str(item) for item in value.get(bucket) or [])
    parts.extend(str(item) for item in manifest.get("relevantFiles") or [])
    parts.append(str(manifest.get("implementationGuidance") or ""))
    return " ".join(parts).casefold()


def _contains_terms(diff: dict[str, Any], manifest: dict[str, Any], terms: tuple[str, ...]) -> bool:
    text = _evidence_text(diff, manifest)
    return any(term in text for term in terms)


def _validation_text(validation: dict[str, Any]) -> str:
    values = [validation.get("violations") or [], validation.get("recommendations") or [], validation.get("warnings") or []]
    return " ".join(str(value) for value in values).casefold()


def _add(activities: dict[str, dict[str, Any]], activity: str, priority: str, reason: str, evidence: str) -> None:
    existing = activities.get(activity)
    ranks = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    if not existing:
        activities[activity] = {"type": activity, "required": True, "priority": priority, "reasons": [reason], "evidence": [evidence]}
        return
    if ranks[priority] > ranks[existing["priority"]]:
        existing["priority"] = priority
    existing["reasons"] = list(dict.fromkeys([*existing["reasons"], reason]))
    existing["evidence"] = list(dict.fromkeys([*existing["evidence"], evidence]))


def _rule(rules: list[dict[str, Any]], rule_id: str, priority: int, reason: str) -> None:
    rules.append({"ruleId": rule_id, "priority": priority, "matched": True, "reason": reason})


def _flag_name(name: str) -> str:
    return "".join(name.split())


def _request_reason(activities: dict[str, dict[str, Any]], counts: dict[str, int], ui_change: bool) -> str:
    changed = [name for name, count in counts.items() if count]
    if ui_change and "UI" not in changed:
        changed.append("UI")
    return f"QA is required for {', '.join(changed) or 'semantic engineering'} changes; planned {len(activities)} test activities."


def _confidence(diff: dict[str, Any], validation: dict[str, Any], activities: dict[str, dict[str, Any]]) -> float:
    diff_confidence = float(diff.get("confidence") or 0.8)
    validation_confidence = float(validation.get("confidence") or 0.85)
    return max(0.5, min(0.99, (diff_confidence + validation_confidence) / 2 + min(0.06, len(activities) * 0.01)))
