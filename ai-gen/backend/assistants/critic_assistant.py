"""Critic stage for structured review of stage outputs."""

from __future__ import annotations


def run_critic_assistant(
    ba_output: dict | None = None,
    ui_output: dict | None = None,
    dev_output: dict | None = None,
    test_output: dict | None = None,
) -> dict:
    """Flag ambiguity, missing coverage, or risky mismatches without rewriting outputs."""

    findings: list[dict] = []
    if ba_output:
        if not ba_output.get("acceptance_criteria"):
            findings.append(_finding("missing_acceptance_criteria", "medium", "Requirement is missing clear acceptance criteria.", "ba"))
        if ba_output.get("unknowns"):
            findings.append(_finding("ambiguity", "medium", "Requirement still has unresolved questions.", "ba"))
    if ui_output and not ui_output.get("skippable"):
        if not ui_output.get("fields") and ui_output.get("screen_type") == "form":
            findings.append(_finding("weak_scope", "medium", "UI form output is missing field definitions.", "ui"))
        if ui_output.get("unknowns"):
            findings.append(_finding("ambiguity", "medium", "UI stage still has open questions that could affect implementation.", "ui"))
    if dev_output:
        if not dev_output.get("scope"):
            findings.append(_finding("weak_scope", "high", "Development scope is too broad or missing.", "dev"))
        if _looks_sensitive(dev_output.get("flow")) and not dev_output.get("constraints"):
            findings.append(_finding("risk", "high", "Sensitive flow is missing explicit safety constraints.", "dev"))
        if _phone_email_conflict(ba_output, ui_output, dev_output):
            findings.append(
                _finding(
                    "conflict",
                    "high",
                    "The task looks phone-based, but the current flow still points to email/password behavior.",
                    "dev",
                )
            )
        if dev_output.get("react", {}).get("observe", {}).get("repo_context_available") and not dev_output.get("selected_files"):
            findings.append(_finding("weak_scope", "medium", "Repo-aware task is missing selected files.", "dev"))
        findings.extend(_semantic_findings(ba_output, ui_output, dev_output))
    if test_output:
        types = {case.get("type") for case in test_output.get("test_cases", [])}
        for expected in {"positive", "negative", "edge"}:
            if expected not in types:
                findings.append(_finding("missing_test", "medium", f"Test coverage is missing a {expected} case.", "test"))
        if not test_output.get("test_cases"):
            findings.append(_finding("missing_test", "high", "No test cases were produced.", "test"))

    overall_risk = _overall_risk(findings)
    has_blocking = any(item["severity"] == "blocking" for item in findings)
    decision = "needs_revision" if has_blocking else "approve_candidate"
    return {
        "assistant": "critic",
        "overall_risk": overall_risk,
        "findings": findings,
        "recommended_changes": _recommended_changes(findings),
        "decision": decision,
        "react": {
            "reason": {
                "known": [stage for stage, output in [("ba", ba_output), ("ui", ui_output), ("dev", dev_output), ("test", test_output)] if output],
                "missing": [finding["message"] for finding in findings[:4]],
                "goal": "Check each generated stage for ambiguity, scope drift, or missing safety coverage.",
            },
            "act": {"finding_count": len(findings)},
            "observe": {"overall_risk": overall_risk},
            "decision": "needs_revision" if has_blocking else "ready_for_approval",
        },
    }


def _finding(finding_type: str, severity: str, message: str, target_stage: str) -> dict:
    return {
        "id": _finding_id(finding_type, target_stage, message),
        "type": finding_type,
        "severity": _normalize_severity(severity),
        "message": message,
        "target_stage": target_stage,
        "source_stage": target_stage,
        "status": "open",
    }


def _overall_risk(findings: list[dict]) -> str:
    if any(item["severity"] == "blocking" for item in findings):
        return "high"
    if any(item["severity"] == "warning" for item in findings):
        return "medium"
    return "low"


def _recommended_changes(findings: list[dict]) -> list[str]:
    recommendations: list[str] = []
    for finding in findings:
        if finding["type"] == "missing_acceptance_criteria":
            recommendations.append("Add concrete acceptance criteria before approving downstream stages.")
        elif finding["type"] == "weak_scope":
            recommendations.append("Narrow the stage output to a smaller, clearer scope.")
        elif finding["type"] == "missing_test":
            recommendations.append("Add the missing test coverage before sign-off.")
        elif finding["type"] == "conflict":
            recommendations.append("Resolve the flow or variant conflict before implementation starts.")
        else:
            recommendations.append("Resolve the open question before approval.")
    return _dedupe(recommendations)


def _phone_email_conflict(ba_output: dict | None, ui_output: dict | None, dev_output: dict | None) -> bool:
    variants = set((ba_output or {}).get("variants", []) + (dev_output or {}).get("variants", []))
    variant = (ba_output or {}).get("variant") or (dev_output or {}).get("variant") or ""
    if "phone_otp" not in variants and variant != "phone_number":
        return False
    values = []
    if ui_output:
        values.extend(field.get("name", "") for field in ui_output.get("fields", []))
    if dev_output:
        values.extend([dev_output.get("flow", ""), dev_output.get("surface", ""), dev_output.get("task_summary", "")])
    lowered = " ".join(str(value) for value in values).lower()
    return "email" in lowered or "password" in lowered


def _looks_sensitive(flow: str | None) -> bool:
    return (flow or "") in {"login", "signup", "session", "payment"}


def _semantic_findings(ba_output: dict | None, ui_output: dict | None, dev_output: dict | None) -> list[dict]:
    findings: list[dict] = []
    flows = set((ba_output or {}).get("flows", []) + (dev_output or {}).get("flows", []))
    variants = set((ba_output or {}).get("variants", []) + (dev_output or {}).get("variants", []))
    surfaces = set((dev_output or {}).get("surfaces", []))
    fields = set()
    if ui_output:
        fields.update(field.get("name", "") for field in ui_output.get("fields", []))
    if "phone_otp" in variants:
        if "otp" not in fields:
            findings.append(_finding("missing_critical_field", "high", "Phone OTP flow is missing the otp field.", "ui"))
        if "email_password" in variants:
            findings.append(_finding("conflicting_variants", "high", "Phone OTP and email_password variants conflict.", "dev"))
    if "dashboard" in flows and "authentication" in surfaces and "ui_screen" not in surfaces:
        findings.append(_finding("semantic_mismatch", "medium", "Dashboard task is mapped too narrowly to authentication.", "dev"))
    if any(surface and surface not in {"ui_screen", "ui_validation", "ui_state", "api_controller", "api_validation", "service_logic", "database", "authentication", "authorization", "workflow", "notification_flow"} for surface in surfaces):
        findings.append(_finding("unsupported_surface", "medium", "Refinement includes an unsupported surface.", "dev"))
    return findings


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _normalize_severity(severity: str) -> str:
    mapping = {
        "high": "blocking",
        "medium": "warning",
        "low": "suggestion",
        "blocking": "blocking",
        "warning": "warning",
        "suggestion": "suggestion",
    }
    return mapping.get(str(severity).strip().lower(), "warning")


def _finding_id(finding_type: str, target_stage: str, message: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "_"
        for character in f"{target_stage}_{finding_type}_{message}".lower()
    )
    normalized = "_".join(part for part in normalized.split("_") if part)
    return f"finding_{normalized[:80]}"
