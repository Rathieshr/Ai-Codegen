from __future__ import annotations

CORE_CAPABILITIES = [
    "Operational Awareness",
    "Fault Monitoring",
    "Alert Management",
    "Notification Management",
    "Event Management",
    "Outage Investigation",
    "Reliability Analytics",
    "Analytics",
    "Trend Analysis",
    "Asset Health",
    "Authentication",
    "Authorization",
    "User Management",
    "Firmware Management",
    "Deployment",
    "Compliance",
    "Device Management",
    "Audit History",
    "Audit Logging",
    "Telemetry",
    "Reporting",
    "Search and Filtering",
    "Export and Reporting",
]

CAPABILITY_RULES: dict[str, dict[str, list[str]]] = {
    "Operational Awareness": {
        "keywords": ["live operations", "live status", "operational status", "dashboard view", "dashboard visibility", "production health", "equipment status", "operations monitoring", "operational visibility", "operator visibility", "shared status", "status center", "alarm center"],
        "modules": ["Reporting", "Telemetry", "Dashboard"],
        "flows": ["Live Status Review", "Operations Monitoring"],
    },
    "Fault Monitoring": {
        "keywords": ["critical fault", "fault detection", "fault event", "severity", "event status", "fault type"],
        "modules": ["Fault Monitoring", "Telemetry", "Device Health"],
        "flows": ["Fault Event Review", "Fault Detail Review"],
    },
    "Alert Management": {
        "keywords": ["alert", "alarm", "acknowledge", "escalation", "response"],
        "modules": ["Fault Monitoring", "Notifications", "Audit"],
        "flows": ["Alert Review", "Alert Acknowledgement", "Escalation Review"],
    },
    "Notification Management": {
        "keywords": ["notification", "notify", "delivery", "subscription", "message", "acknowledgement", "alarm center"],
        "modules": ["Notification", "Notifications", "Audit"],
        "flows": ["Notification Review", "Alert Acknowledgement", "Alert Review"],
    },
    "Event Management": {
        "keywords": ["event", "incident", "history", "priority", "lifecycle", "event status", "timeline"],
        "modules": ["Fault Monitoring", "Audit", "Reporting"],
        "flows": ["Event Timeline Review", "Alert Review", "Fault Event Review"],
    },
    "Outage Investigation": {
        "keywords": ["outage", "investigation", "triage", "fault event", "root cause", "event timeline"],
        "modules": ["Fault Monitoring", "Telemetry", "Device Health", "Investigation Notes"],
        "flows": ["Outage Investigation", "Device Health Review", "Event Timeline Review"],
    },
    "Reliability Analytics": {
        "keywords": ["analytics", "trend", "kpi", "metric", "reliability", "analysis", "severity distribution", "response metrics"],
        "modules": ["Reporting", "Analytics", "Asset Health", "Telemetry Aggregation"],
        "flows": ["Reliability Trend Review", "Analytics Review"],
    },
    "Asset Health": {
        "keywords": ["asset", "asset health", "device health", "condition", "fleet"],
        "modules": ["Asset Health", "Device Management", "Telemetry"],
        "flows": ["Device Health Review", "Telemetry Review"],
    },
    "Analytics": {
        "keywords": ["analytics", "insight", "data analysis", "consumption analytics", "operational analytics"],
        "modules": ["Analytics", "Reporting", "Telemetry Aggregation"],
        "flows": ["Analytics Review", "Reliability Trend Review"],
    },
    "Trend Analysis": {
        "keywords": ["trend", "trend analysis", "forecast", "historical analysis", "severity distribution"],
        "modules": ["Analytics", "Reporting", "Telemetry Aggregation"],
        "flows": ["Reliability Trend Review", "Analytics Review"],
    },
    "Device Health": {
        "keywords": ["device health", "device condition", "equipment status", "device status"],
        "modules": ["Device Management", "Asset Health", "Telemetry"],
        "flows": ["Device Health Review", "Telemetry Review"],
    },
    "Telemetry": {
        "keywords": ["telemetry", "signal", "reading", "freshness", "stream", "meter"],
        "modules": ["Telemetry", "Telemetry Aggregation"],
        "flows": ["Telemetry Review"],
    },
    "Telemetry Review": {
        "keywords": ["telemetry", "signal", "reading", "freshness", "meter"],
        "modules": ["Telemetry"],
        "flows": ["Telemetry Review"],
    },
    "Reporting": {
        "keywords": ["report", "summary", "visibility", "status report"],
        "modules": ["Reporting"],
        "flows": ["Export and Reporting"],
    },
    "Dashboard Monitoring": {
        "keywords": ["dashboard", "live view", "workspace", "panel"],
        "modules": ["Dashboard", "Fault Monitoring", "Telemetry"],
        "flows": ["Dashboard Monitoring"],
    },
    "Notification": {
        "keywords": ["notify", "notification", "message", "email", "sms"],
        "modules": ["Notification"],
        "flows": ["Notification Review", "Alert Review"],
    },
    "Authentication": {
        "keywords": ["login", "authentication", "sign in", "otp", "password", "session", "token"],
        "modules": ["Authentication"],
        "flows": ["Authentication", "Token Refresh"],
    },
    "Authorization": {
        "keywords": ["permission", "unauthorized", "access denied", "role", "authorization"],
        "modules": ["Authentication", "Authorization"],
        "flows": ["Access Review"],
    },
    "User Management": {
        "keywords": ["user management", "user administration", "account", "admin", "identity", "role", "permission"],
        "modules": ["Authentication", "Authorization", "Audit"],
        "flows": ["Access Review", "Authentication"],
    },
    "Firmware Management": {
        "keywords": ["firmware", "version", "rollout", "upgrade", "rollback", "compliance", "device update"],
        "modules": ["Firmware", "Device Management"],
        "flows": ["Firmware Rollout"],
    },
    "Deployment": {
        "keywords": ["deployment", "rollout", "release", "upgrade", "distribution"],
        "modules": ["Firmware", "Device Management"],
        "flows": ["Firmware Rollout", "Device Registration"],
    },
    "Compliance": {
        "keywords": ["compliance", "policy", "version", "regulation", "auditability"],
        "modules": ["Firmware", "Audit", "Reporting"],
        "flows": ["Firmware Rollout", "Audit Review"],
    },
    "Device Management": {
        "keywords": ["device", "registration", "provisioning", "device update", "device status"],
        "modules": ["Device Management"],
        "flows": ["Device Registration", "Device Health Review"],
    },
    "Audit History": {
        "keywords": ["audit", "history", "trace", "who changed", "approval"],
        "modules": ["Audit", "Reporting"],
        "flows": ["Audit Review"],
    },
    "Audit Logging": {
        "keywords": ["audit logging", "audit", "history", "trace", "compliance history"],
        "modules": ["Audit", "Reporting", "Authorization"],
        "flows": ["Audit Review", "Access Review"],
    },
    "Search and Filtering": {
        "keywords": ["search", "filter", "sort", "find", "query"],
        "modules": ["Search", "Reporting"],
        "flows": ["Search and Filtering"],
    },
    "Export and Reporting": {
        "keywords": ["export", "download", "csv", "pdf", "report"],
        "modules": ["Reporting"],
        "flows": ["Export and Reporting"],
    },
}

REJECTION_RULES: dict[str, dict[str, list[str] | str]] = {
    "Notification Management": {
        "required": ["notification", "notify", "delivery", "subscription", "message", "acknowledgement", "alarm", "alert"],
        "reason": "Intent does not mention notifications, message delivery, acknowledgement, alerts, or alarm handling.",
    },
    "Event Management": {
        "required": ["event", "incident", "history", "timeline", "priority", "status"],
        "reason": "Intent does not mention event lifecycle, incident handling, timeline, history, priority, or event status.",
    },
    "Firmware Management": {
        "required": ["firmware", "version", "rollout", "upgrade", "rollback", "compliance", "device update"],
        "reason": "Intent does not mention firmware, version, rollout, upgrade, rollback, compliance, or device update.",
    },
    "Authentication": {
        "required": ["login", "authentication", "sign in", "otp", "password", "session", "token"],
        "reason": "Intent does not mention login, authentication, token, session, OTP, or password behavior.",
    },
    "Authorization": {
        "required": ["permission", "unauthorized", "access denied", "role", "authorization"],
        "reason": "Intent does not mention permissions, roles, authorization, or access failure behavior.",
    },
    "Reliability Analytics": {
        "required": ["analytics", "trend", "kpi", "metric", "reliability", "analysis"],
        "reason": "Intent does not mention analytics, trends, metrics, KPIs, or reliability analysis.",
    },
    "Asset Health": {
        "required": ["asset", "health", "condition", "fleet"],
        "reason": "Intent does not mention asset health, condition, fleet health, or health monitoring outcomes.",
    },
    "Analytics": {
        "required": ["analytics", "analysis", "insight", "data"],
        "reason": "Intent does not mention analytics, data analysis, or insights.",
    },
    "Trend Analysis": {
        "required": ["trend", "history", "forecast", "distribution", "metric"],
        "reason": "Intent does not mention trends, historical analysis, forecasting, or distributions.",
    },
    "User Management": {
        "required": ["user", "account", "admin", "identity", "role", "permission"],
        "reason": "Intent does not mention users, accounts, identities, admin behavior, roles, or access management.",
    },
    "Deployment": {
        "required": ["deployment", "rollout", "release", "upgrade", "distribution"],
        "reason": "Intent does not mention deployment, rollout, release, upgrade, or distribution behavior.",
    },
    "Compliance": {
        "required": ["compliance", "policy", "regulation", "audit", "version"],
        "reason": "Intent does not mention compliance, policy, regulation, audit, or version governance.",
    },
    "Telemetry": {
        "required": ["telemetry", "signal", "reading", "freshness", "meter"],
        "reason": "Intent does not mention telemetry, signals, readings, or freshness data.",
    },
    "Reporting": {
        "required": ["report", "summary", "export", "visibility"],
        "reason": "Intent does not mention reporting, export, summaries, or visibility outputs.",
    },
    "Audit Logging": {
        "required": ["audit", "history", "trace", "compliance"],
        "reason": "Intent does not mention audit logging, traceability, history, or compliance evidence.",
    },
}

CAPABILITY_PURPOSE_GROUPS: dict[str, str] = {
    "Operational Awareness": "awareness",
    "Dashboard Monitoring": "dashboard",
    "Reporting": "reporting",
    "Export and Reporting": "reporting",
    "Alert Management": "alerting",
    "Notification Management": "notification_management",
    "Event Management": "event_management",
    "Outage Investigation": "investigation",
    "Fault Monitoring": "fault_monitoring",
    "Asset Health": "asset_health",
    "Device Health": "asset_health",
    "Authentication": "access",
    "Authorization": "access",
    "User Management": "user_management",
    "Firmware Management": "firmware",
    "Deployment": "deployment",
    "Compliance": "compliance",
    "Device Management": "device",
    "Analytics": "analytics",
    "Trend Analysis": "trend_analysis",
    "Telemetry": "telemetry",
    "Audit Logging": "audit_logging",
}

CAPABILITY_CLASSIFICATIONS: dict[str, str] = {
    "Operational Awareness": "Supporting",
    "Fault Monitoring": "Business",
    "Alert Management": "Business",
    "Notification Management": "Business",
    "Event Management": "Business",
    "Outage Investigation": "Business",
    "Reliability Analytics": "Analytics",
    "Analytics": "Analytics",
    "Trend Analysis": "Analytics",
    "Asset Health": "Business",
    "Device Health": "Business",
    "Telemetry": "Infrastructure",
    "Reporting": "Analytics",
    "Authentication": "Security",
    "Authorization": "Security",
    "User Management": "Business",
    "Firmware Management": "Business",
    "Deployment": "Infrastructure",
    "Compliance": "Security",
    "Device Management": "Business",
    "Audit History": "Supporting",
    "Audit Logging": "Supporting",
    "Search and Filtering": "Supporting",
    "Export and Reporting": "Analytics",
}

CAPABILITY_BUSINESS_PRIORITY: dict[str, int] = {
    "Business": 100,
    "Analytics": 86,
    "Supporting": 76,
    "Security": 74,
    "Infrastructure": 68,
}

SYSTEM_FLOW_NAMES = {
    "Analytics Platform",
    "Mobile Application",
    "Operations Dashboard",
    "Application",
    "Backend API",
    "Mobile App",
    "Backend",
    "Web Portal",
}

VALID_FLOW_NAMES = {
    "Fault Event Review",
    "Fault Detail Review",
    "Alert Review",
    "Alert Acknowledgement",
    "Escalation Review",
    "Outage Investigation",
    "Device Health Review",
    "Event Timeline Review",
    "Live Status Review",
    "Operations Monitoring",
    "Reliability Trend Review",
    "Analytics Review",
    "Telemetry Review",
    "Token Refresh",
    "Access Review",
    "Firmware Rollout",
    "Device Registration",
}

CAPABILITY_CATEGORY_ALIASES = {
    "Critical Fault Detection": "Fault Monitoring",
    "Critical Fault Monitoring": "Fault Monitoring",
    "Monitoring": "Fault Monitoring",
    "Alerting": "Alert Management",
    "Notification": "Notification Management",
    "Investigation": "Outage Investigation",
    "Analytics": "Analytics",
    "Dashboard Monitoring": "Operational Awareness",
    "Reporting": "Reporting",
    "Audit": "Audit Logging",
    "Compliance Management": "Compliance",
}


def canonical_capability(name: str) -> str:
    cleaned = " ".join(str(name or "").split())
    return CAPABILITY_CATEGORY_ALIASES.get(cleaned, cleaned)


def capability_classification(name: str) -> str:
    return CAPABILITY_CLASSIFICATIONS.get(canonical_capability(name), "Supporting")


def capability_business_priority(name: str) -> int:
    canonical = canonical_capability(name)
    if canonical == "Deployment":
        return 90
    if canonical == "Device Management":
        return 88
    if canonical == "Telemetry":
        return 84
    if canonical == "Trend Analysis":
        return 90
    return CAPABILITY_BUSINESS_PRIORITY.get(capability_classification(canonical), 70)


def is_system_flow_name(name: str) -> bool:
    return " ".join(str(name or "").split()) in SYSTEM_FLOW_NAMES
