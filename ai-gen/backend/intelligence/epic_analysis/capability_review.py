from __future__ import annotations

from typing import Any


CAPABILITY_RESPONSIBILITIES: dict[str, list[str]] = {
    "Operational Awareness": ["Show live operational status", "Surface active events", "Connect event state to affected assets", "Support operational drill-down"],
    "Fault Monitoring": ["Detect fault events", "Classify severity", "Surface critical events", "Support event review", "Support event filtering"],
    "Alert Management": ["Notify operators about actionable events", "Support acknowledgement", "Support escalation", "Suppress duplicate active alerts"],
    "Outage Investigation": ["Start investigation from an event", "Correlate event and device context", "Support investigation filtering", "Preserve investigation notes"],
    "Reliability Analytics": ["Summarize reliability trends", "Compare operating periods", "Highlight reliability signals", "Support prioritization decisions"],
    "Asset Health": ["Show device health state", "Correlate health with events", "Highlight stale health data", "Support device health review"],
    "Telemetry": ["Expose telemetry freshness", "Detect telemetry gaps", "Show ingestion status", "Support telemetry quality review"],
    "Firmware Management": ["Show rollout status", "Track version exceptions", "Surface failed upgrades", "Support rollback visibility"],
}


CAPABILITY_SCOPE: dict[str, tuple[list[str], list[str]]] = {
    "Operational Awareness": (
        ["Live status", "Active event overview", "Operational drill-down", "Shared status context"],
        ["Firmware rollout", "Historical analytics", "Root-cause investigation"],
    ),
    "Fault Monitoring": (
        ["Fault detection", "Severity classification", "Event list", "Event details"],
        ["Alert notifications", "Root-cause investigation", "Historical analytics", "Firmware updates"],
    ),
    "Alert Management": (
        ["Alert delivery", "Acknowledgement", "Escalation state", "Duplicate alert handling"],
        ["Fault classification", "Outage investigation notes", "Reliability trends", "Firmware updates"],
    ),
    "Outage Investigation": (
        ["Investigation entry point", "Event timeline", "Device context", "Investigation notes"],
        ["Alert routing", "Firmware rollout", "Reliability trend dashboards"],
    ),
    "Reliability Analytics": (
        ["Trend dashboards", "Period comparison", "Reliability metrics", "Analytics data quality"],
        ["Live fault triage", "Alert acknowledgement", "Firmware deployment"],
    ),
    "Asset Health": (
        ["Health score", "Device state", "Health detail review", "Stale health data"],
        ["Alert delivery", "Firmware version rollout", "Reliability trend reports"],
    ),
    "Telemetry": (
        ["Telemetry freshness", "Missing readings", "Signal quality", "Ingestion state"],
        ["Fault severity ownership", "Alert escalation", "Firmware updates"],
    ),
    "Firmware Management": (
        ["Firmware version status", "Rollout progress", "Upgrade failure reason", "Rollback visibility"],
        ["Fault investigation", "Reliability analytics", "Alert ownership"],
    ),
}


def buildCapabilityReview(epic_analysis: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    capabilities = epic_analysis.get("requiredCapabilities") if isinstance(epic_analysis.get("requiredCapabilities"), list) else []
    priorities = {
        str(item.get("name") or ""): item
        for item in epic_analysis.get("capabilityPriority", [])
        if isinstance(item, dict)
    }
    relationships = [item for item in epic_analysis.get("capabilityRelationships", []) if isinstance(item, dict)]
    reviews = [
        _review_item(index, capability, priorities.get(str(capability.get("name") or "")), relationships, profile)
        for index, capability in enumerate(capabilities, start=1)
        if isinstance(capability, dict) and capability.get("name")
    ]
    reviews = _dependency_order(reviews)
    validation = validateCapabilityReviews(reviews)
    return {
        "capabilities": reviews,
        "diagnostics": {
            "capabilityCount": len(reviews),
            "approved": len([item for item in reviews if item["status"] == "Approved"]),
            "rejected": len([item for item in reviews if item["status"] == "Rejected"]),
            "averageConfidence": round(sum(float(item.get("confidence") or 0) for item in reviews) / len(reviews), 2) if reviews else 0,
            "repositoryEvidence": sum(len(item.get("repositoryEvidence") or []) for item in reviews),
            "graphRelationships": len(relationships),
            "planningReadiness": "Ready For Review" if not validation["blockingIssues"] else "Needs Review",
            "validationIssues": validation["issues"],
        },
        "dependencyGraph": [
            {
                "source": item.get("source"),
                "relationship": item.get("relationship"),
                "target": item.get("target"),
                "reason": item.get("reason"),
            }
            for item in relationships
        ],
    }


def validateCapabilityReviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    responsibility_owner: dict[str, str] = {}
    for item in reviews:
        name = str(item.get("capabilityName") or "")
        if name in seen_names:
            issues.append({"severity": "Rejected", "capability": name, "reason": "Duplicate capability name."})
        seen_names.add(name)
        if not item.get("businessPurpose"):
            issues.append({"severity": "Rejected", "capability": name, "reason": "Missing business purpose."})
        if not item.get("repositoryEvidence"):
            issues.append({"severity": "NeedsReview", "capability": name, "reason": "Repository evidence is weak or missing."})
        for responsibility in item.get("responsibilities") or []:
            key = str(responsibility).lower()
            owner = responsibility_owner.get(key)
            if owner and owner != name:
                issues.append({"severity": "Rejected", "capability": name, "reason": f"Responsibility overlaps with {owner}.", "responsibility": responsibility})
            else:
                responsibility_owner[key] = name
    return {
        "issues": issues,
        "blockingIssues": [item for item in issues if item.get("severity") == "Rejected"],
    }


def _review_item(
    index: int,
    capability: dict[str, Any],
    priority: dict[str, Any] | None,
    relationships: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    name = str(capability.get("name") or "").strip()
    in_scope, out_of_scope = CAPABILITY_SCOPE.get(name, ([name], ["Unrelated capabilities"]))
    related = _related_context(name, profile)
    return {
        "capabilityId": _capability_id(name, index),
        "capabilityName": name,
        "businessPurpose": str(capability.get("reason") or f"{name} is required to satisfy the epic business outcome."),
        "responsibilities": CAPABILITY_RESPONSIBILITIES.get(name, [f"Own {name.lower()} behavior", f"Define {name.lower()} review states"]),
        "businessValue": _business_value(name),
        "priority": str((priority or {}).get("priority") or _default_priority(index)),
        "inScope": list(in_scope),
        "outOfScope": list(out_of_scope),
        "dependencies": _dependencies_for(name, relationships),
        "supports": _supports_for(name, relationships),
        "repositoryEvidence": _evidence_for(capability, related),
        "relatedModules": related["modules"],
        "relatedFlows": related["flows"],
        "relatedApplications": related["applications"],
        "estimatedFeatures": 1,
        "confidence": round(float(capability.get("confidence") or 0.72), 2),
        "status": "Pending",
        "reviewComments": [],
        "explainability": {
            "whyExists": str(capability.get("reason") or f"{name} was selected from Epic Analysis."),
            "whyRequired": f"{name} contributes to the epic planning boundary and should be reviewed before feature generation.",
            "businessProblemSolved": _business_problem(name),
            "excludedScope": list(out_of_scope),
        },
    }


def _dependency_order(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority_weight = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    dependency_names = {dependency for item in reviews for dependency in item.get("dependencies", [])}
    return sorted(
        reviews,
        key=lambda item: (
            0 if item.get("capabilityName") in dependency_names else 1,
            priority_weight.get(str(item.get("priority")), 4),
            str(item.get("capabilityName") or ""),
        ),
    )


def _related_context(name: str, profile: dict[str, Any]) -> dict[str, list[str]]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    modules = _match_registry(name, registry.get("modules", []), "module")
    flows = _match_registry(name, registry.get("flows", []), "flow")
    applications = [
        str(app.get("name") or app)
        for app in profile.get("applications", [])[:4]
        if app
    ] or [str(item) for item in registry.get("applications", [])[:4] if item]
    return {"modules": modules, "flows": flows, "applications": applications}


def _match_registry(name: str, values: Any, kind: str) -> list[str]:
    tokens_by_capability = {
        "Operational Awareness": ["operation", "dashboard", "status", "monitor"],
        "Fault Monitoring": ["fault", "event", "telemetry"],
        "Alert Management": ["alert", "notification", "fault"],
        "Outage Investigation": ["outage", "investigation", "fault", "health"],
        "Reliability Analytics": ["analytics", "report", "trend", "reliability"],
        "Asset Health": ["asset", "health", "device"],
        "Telemetry": ["telemetry", "ingestion", "quality"],
        "Firmware Management": ["firmware", "upgrade", "rollout"],
    }.get(name, [name.lower()])
    result = []
    for value in values if isinstance(values, list) else []:
        text = str(value)
        lowered = text.lower()
        if any(token in lowered for token in tokens_by_capability):
            result.append(text)
    return result[:4]


def _dependencies_for(name: str, relationships: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("source"))
        for item in relationships
        if item.get("target") == name and item.get("relationship") in {"supports", "depends_on"}
    ]


def _supports_for(name: str, relationships: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("target"))
        for item in relationships
        if item.get("source") == name and item.get("relationship") in {"supports", "depends_on"}
    ]


def _evidence_for(capability: dict[str, Any], related: dict[str, list[str]]) -> list[str]:
    evidence = [str(item) for item in capability.get("repositoryEvidence", []) if item]
    evidence.extend(related.get("modules", [])[:2])
    evidence.extend(related.get("flows", [])[:2])
    return list(dict.fromkeys(evidence))[:8]


def _business_value(name: str) -> str:
    values = {
        "Operational Awareness": "Shared live operating context for faster decisions.",
        "Fault Monitoring": "Faster detection and review of critical operating conditions.",
        "Alert Management": "Reduced response time through actionable operator notifications.",
        "Outage Investigation": "Faster root-cause analysis and outage triage.",
        "Reliability Analytics": "Better prioritization through reliability trends and operational insight.",
        "Asset Health": "Improved decisions through correlated device health.",
        "Telemetry": "Higher confidence in decisions through trusted telemetry quality.",
        "Firmware Management": "Safer rollout operations with visible upgrade status.",
    }
    return values.get(name, f"Improved {name.lower()} business outcomes.")


def _business_problem(name: str) -> str:
    problems = {
        "Fault Monitoring": "Critical events are not visible early enough.",
        "Alert Management": "Operators do not know which events require immediate action.",
        "Outage Investigation": "Teams lose time correlating event context during outages.",
        "Reliability Analytics": "Leaders lack trend evidence for prioritization.",
        "Operational Awareness": "Operational status is spread across disconnected views.",
    }
    return problems.get(name, f"{name} is not yet structured as an approved planning capability.")


def _default_priority(index: int) -> str:
    if index <= 2:
        return "Critical"
    if index <= 4:
        return "High"
    if index <= 6:
        return "Medium"
    return "Low"


def _capability_id(name: str, index: int) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"capability_{slug or index}"
