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


def buildCapabilityReview(epic: dict[str, Any], epic_analysis: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    capabilities = epic_analysis.get("requiredCapabilities") if isinstance(epic_analysis.get("requiredCapabilities"), list) else []
    priorities = {
        str(item.get("name") or ""): item
        for item in epic_analysis.get("capabilityPriority", [])
        if isinstance(item, dict)
    }
    relationships = [item for item in epic_analysis.get("capabilityRelationships", []) if isinstance(item, dict)]
    reviews = [
        _review_item(index, capability, priorities.get(str(capability.get("name") or "")), relationships, epic, epic_analysis, profile)
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
    epic: dict[str, Any],
    epic_analysis: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    name = str(capability.get("name") or "").strip()
    in_scope, out_of_scope = CAPABILITY_SCOPE.get(name, ([name], ["Unrelated capabilities"]))
    related = _related_context(name, profile)
    contextual = _contextual_capability_review(name, epic, epic_analysis, related)
    return {
        "capabilityId": _capability_id(name, index),
        "capabilityName": contextual["name"],
        "capabilityCategory": name,
        "suggestedFeatureTitle": contextual["featureTitle"],
        "businessPurpose": contextual["businessPurpose"] or str(capability.get("reason") or f"{name} is required to satisfy the epic business outcome."),
        "responsibilities": contextual["responsibilities"] or CAPABILITY_RESPONSIBILITIES.get(name, [f"Own {name.lower()} behavior", f"Define {name.lower()} review states"]),
        "businessValue": _business_value(name),
        "priority": str((priority or {}).get("priority") or _default_priority(index)),
        "inScope": contextual["inScope"] or list(in_scope),
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
            "whyExists": contextual["whyExists"] or str(capability.get("reason") or f"{name} was selected from Epic Analysis."),
            "whyRequired": f"{contextual['name']} contributes to the epic planning boundary and should be reviewed before feature generation.",
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


def _contextual_capability_review(
    capability: str,
    epic: dict[str, Any],
    epic_analysis: dict[str, Any],
    related: dict[str, list[str]],
) -> dict[str, Any]:
    corpus = _review_corpus(epic, epic_analysis, related)
    if _is_device_health_dashboard(corpus):
        mapping = {
            "Operational Awareness": {
                "name": "Device Health Overview",
                "featureTitle": "Device Health Overview",
                "businessPurpose": "Provide operations users with a real-time overview of device health, communication status, and operational alerts so unhealthy devices can be identified and acted on before failures occur.",
                "responsibilities": ["Show overall device health status", "Summarize unhealthy and attention-needed devices", "Highlight communication status", "Support drill-down into affected devices"],
                "inScope": ["Health overview", "Summary counts by status", "Communication state visibility", "Dashboard drill-down"],
                "whyExists": "The epic is centered on modernizing a device health dashboard, so the first capability should give operators a clear health overview."
            },
            "Fault Monitoring": {
                "name": "Health Status Filtering",
                "featureTitle": "Health Status Filtering",
                "businessPurpose": "Allow operators to filter device health results by status, severity, attention-needed state, and operational condition so the dashboard can isolate the devices that require action.",
                "responsibilities": ["Filter by health state", "Filter by severity", "Support attention-needed views", "Preserve filtered dashboard context"],
                "inScope": ["Status filtering", "Severity filtering", "Attention-needed filtering", "Filter persistence"],
                "whyExists": "Device health dashboards need fast filtering so operators can isolate unhealthy devices instead of scanning the full grid."
            },
            "Telemetry": {
                "name": "Offline Device Detection",
                "featureTitle": "Offline Device Detection",
                "businessPurpose": "Identify offline, stale, or non-reporting devices from telemetry freshness and communication signals so operators can react before health issues become failures.",
                "responsibilities": ["Detect stale telemetry", "Flag offline devices", "Expose freshness state", "Highlight communication gaps"],
                "inScope": ["Offline detection", "Telemetry freshness visibility", "Stale communication alerts", "Non-reporting device flags"],
                "whyExists": "Telemetry freshness is a core indicator for device health dashboards and should surface offline devices directly."
            },
            "Asset Health": {
                "name": "Device Detail View",
                "featureTitle": "Device Detail View",
                "businessPurpose": "Allow operators to open a detailed device health view with current status, recent telemetry, communication state, and related operational context.",
                "responsibilities": ["Open device health details", "Show current status and health score", "Display recent telemetry context", "Connect detail view back to dashboard state"],
                "inScope": ["Detail view", "Recent telemetry context", "Health state explanation", "Device-level operational context"],
                "whyExists": "A dashboard modernization effort needs a clear device detail drill-down, not only a top-level summary."
            },
            "Reliability Analytics": {
                "name": "Health Trend Analytics",
                "featureTitle": "Health Trend Analytics",
                "businessPurpose": "Give operations leaders visibility into health trends, degradation patterns, and recurring unhealthy-device cohorts so maintenance can be prioritized proactively.",
                "responsibilities": ["Track health trends over time", "Highlight degradation patterns", "Compare current and previous periods", "Support prioritization decisions"],
                "inScope": ["Trend analytics", "Period comparison", "Health degradation patterns", "Health KPI visibility"],
                "whyExists": "The dashboard should not only show current health, it should also explain whether device health is improving or degrading."
            },
            "Device Management": {
                "name": "Device Search",
                "featureTitle": "Device Search",
                "businessPurpose": "Allow operators to search for a device directly from the health dashboard and jump into the correct health context without scanning the full list.",
                "responsibilities": ["Search devices by identifier", "Support direct dashboard lookup", "Preserve active health context", "Navigate from search to detail"],
                "inScope": ["Device search", "Identifier lookup", "Search-to-detail navigation", "Search state retention"],
                "whyExists": "Operations teams need direct device lookup when the dashboard contains many devices."
            },
            "Event Management": {
                "name": "Health Status Filtering",
                "featureTitle": "Health Status Filtering",
                "businessPurpose": "Allow operators to filter device health results by health status, attention-needed state, communication condition, and operational severity so the dashboard stays focused on the devices that require action.",
                "responsibilities": ["Filter by health status", "Filter by communication state", "Support attention-needed filtering", "Preserve dashboard filter context"],
                "inScope": ["Health status filtering", "Communication-state filtering", "Attention-needed filtering", "Filter persistence"],
                "whyExists": "A health dashboard needs status-based filtering so operators can move from overview into an actionable subset quickly."
            },
            "Alert Management": {
                "name": "Offline Device Detection",
                "featureTitle": "Offline Device Detection",
                "businessPurpose": "Highlight offline, stale, or non-reporting devices from communication status and health signals so operators can detect unhealthy devices before failures escalate.",
                "responsibilities": ["Identify offline devices", "Detect stale reporting", "Surface non-reporting communication status", "Prioritize devices needing intervention"],
                "inScope": ["Offline detection", "Stale reporting visibility", "Communication-state alerts", "Attention-needed prioritization"],
                "whyExists": "When the dashboard centers on communication and health status, operators need a dedicated view of offline and non-reporting devices."
            },
            "Notification Management": {
                "name": "Health Trend Analytics",
                "featureTitle": "Health Trend Analytics",
                "businessPurpose": "Show recurring unhealthy-device patterns and trend signals so operations leaders can identify systemic health problems instead of only reacting to the current state.",
                "responsibilities": ["Show health trends", "Highlight recurring unhealthy-device cohorts", "Support trend-based prioritization", "Expose systemic degradation signals"],
                "inScope": ["Trend visibility", "Recurring issue detection", "Prioritization signals", "Health pattern review"],
                "whyExists": "Dashboard modernization should expose whether health is improving or degrading over time, not only the current snapshot."
            },
            "Authorization": {
                "name": "Role-Based Access",
                "featureTitle": "Role-Based Access",
                "businessPurpose": "Ensure device health dashboard actions and detail visibility respect role-based access so operations users see only the appropriate health context and controls.",
                "responsibilities": ["Restrict dashboard actions by role", "Restrict device detail visibility", "Preserve auditability for restricted views", "Support least-privilege dashboard access"],
                "inScope": ["Role-based visibility", "Role-based actions", "Restricted detail access", "Audit visibility for restricted interactions"],
                "whyExists": "Dashboard modernization often exposes more operational context, so role-based access needs to be explicit."
            },
        }
        if capability in mapping:
            return mapping[capability]
    return {
        "name": capability,
        "featureTitle": capability,
        "businessPurpose": "",
        "responsibilities": [],
        "inScope": [],
        "whyExists": "",
    }


def _review_corpus(epic: dict[str, Any], epic_analysis: dict[str, Any], related: dict[str, list[str]]) -> str:
    parts = [
        epic.get("title"),
        epic.get("description"),
        " ".join(str(item or "") for item in epic_analysis.get("businessGoals", []) or []),
        " ".join(str(item or "") for item in epic_analysis.get("businessProblems", []) or []),
        " ".join(related.get("modules", [])),
        " ".join(related.get("flows", [])),
    ]
    return " ".join(str(part or "").lower() for part in parts if part)


def _is_device_health_dashboard(corpus: str) -> bool:
    return (
        "device health" in corpus
        and any(token in corpus for token in ["health dashboard", "communication status", "operations center", "operations centre"])
    )
