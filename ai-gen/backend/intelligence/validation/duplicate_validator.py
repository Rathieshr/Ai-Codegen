from __future__ import annotations

from typing import Any

from backend.intelligence.capability.capability_rules import canonical_capability

from .validation_report import ValidationIssue
from .validation_utils import clean, names, similarity


def validate_duplicates(artifact: dict[str, Any], existing_siblings: list[dict[str, Any]]) -> tuple[int, list[ValidationIssue]]:
    title = clean(artifact.get("title"))
    description = clean(artifact.get("description"))
    capability = _capability_category(artifact)
    artifact_context = _semantic_context(artifact)
    best_score = 0.0
    best_title = ""
    best_reason = ""
    for sibling in existing_siblings:
        sibling_title = clean(sibling.get("title"))
        sibling_description = clean(sibling.get("description") or sibling.get("purpose"))
        sibling_capability = _capability_category(sibling)
        capability_match = capability and sibling_capability and capability == sibling_capability
        score = max(similarity(title, sibling_title), similarity(f"{title} {description}", f"{sibling_title} {sibling_description}"))
        semantic_score = similarity(artifact_context, _semantic_context(sibling))
        if capability_match:
            score = max(score, semantic_score + 0.18)
        elif capability and sibling_capability and capability != sibling_capability:
            score = min(score, 0.66)
        if (sibling.get("duplicateRisk") or sibling.get("duplicate_risk")) and (capability_match or not (capability and sibling_capability)):
            score = max(score, 0.82)
        if score > best_score:
            best_score = score
            best_title = sibling_title
            best_reason = f"same capability category: {capability}" if capability_match else "semantic overlap"
    duplicate_risk = int(best_score * 100)
    issues: list[ValidationIssue] = []
    if duplicate_risk >= 75:
        issues.append(ValidationIssue("Warning", "Duplicate Detection", f"Artifact is similar to existing sibling: {best_title} ({best_reason}).", "Reuse the existing artifact or explain why a separate artifact is needed."))
    return duplicate_risk, issues


def _capability_category(item: dict[str, Any]) -> str:
    evidence = item.get("generatedUsing") if isinstance(item.get("generatedUsing"), dict) else {}
    raw = (
        clean(item.get("capability_category"))
        or clean(item.get("capability"))
        or (names(evidence.get("capabilities"))[0] if names(evidence.get("capabilities")) else "")
        or _infer_capability_category(clean(item.get("title")), clean(item.get("description") or item.get("purpose")))
    )
    return canonical_capability(raw)


def _infer_capability_category(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    if any(token in text for token in ["firmware", "rollout", "upgrade", "rollback"]):
        return "Firmware Management"
    if any(token in text for token in ["outage", "investigation", "root cause", "timeline"]):
        return "Outage Investigation"
    if any(token in text for token in ["alert", "notification", "acknowledge", "escalation"]):
        return "Alert Management"
    if any(token in text for token in ["critical fault", "fault event", "fault detection", "severity"]):
        return "Fault Monitoring"
    if any(token in text for token in ["analytics", "trend", "metric", "kpi", "reliability"]):
        return "Reliability Analytics"
    if any(token in text for token in ["live", "operational awareness", "operations awareness", "status", "monitoring view"]):
        return "Operational Awareness"
    return ""


def _semantic_context(item: dict[str, Any]) -> str:
    evidence = item.get("generatedUsing") if isinstance(item.get("generatedUsing"), dict) else {}
    parts = [
        clean(item.get("title")),
        clean(item.get("description")),
        clean(item.get("business_goal")),
        clean(item.get("businessValue") or item.get("business_value")),
        clean(item.get("user_problem")),
        clean(item.get("acceptanceCriteria") or item.get("acceptance_criteria")),
        clean(item.get("impacted_modules") or names(evidence.get("modules"))),
        clean(item.get("impacted_flows") or names(evidence.get("flows"))),
    ]
    return " ".join(part for part in parts if part)
