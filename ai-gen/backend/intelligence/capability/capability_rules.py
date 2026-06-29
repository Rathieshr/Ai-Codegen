from __future__ import annotations

CORE_CAPABILITIES = [
    "Operational Awareness",
    "Fault Monitoring",
    "Alert Management",
    "Outage Investigation",
    "Reliability Analytics",
    "Asset Health",
    "Authentication",
    "Authorization",
    "Firmware Management",
    "Device Management",
    "Audit History",
    "Search and Filtering",
    "Export and Reporting",
]

CAPABILITY_RULES: dict[str, dict[str, list[str]]] = {
    "Operational Awareness": {
        "keywords": ["live operations", "live status", "operational status", "dashboard view", "production health", "equipment status", "operations monitoring"],
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
    "Device Health": {
        "keywords": ["device health", "device condition", "equipment status", "device status"],
        "modules": ["Device Management", "Asset Health", "Telemetry"],
        "flows": ["Device Health Review", "Telemetry Review"],
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
    "Firmware Management": {
        "keywords": ["firmware", "version", "rollout", "upgrade", "rollback", "compliance", "device update"],
        "modules": ["Firmware", "Device Management"],
        "flows": ["Firmware Rollout"],
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
}

CAPABILITY_PURPOSE_GROUPS: dict[str, str] = {
    "Operational Awareness": "awareness",
    "Dashboard Monitoring": "dashboard",
    "Reporting": "reporting",
    "Export and Reporting": "reporting",
    "Alert Management": "alerting",
    "Notification": "alerting",
    "Outage Investigation": "investigation",
    "Fault Monitoring": "fault_monitoring",
    "Asset Health": "asset_health",
    "Device Health": "asset_health",
    "Authentication": "access",
    "Authorization": "access",
    "Firmware Management": "firmware",
    "Device Management": "device",
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
    "Notification": "Alert Management",
    "Investigation": "Outage Investigation",
    "Analytics": "Reliability Analytics",
    "Dashboard Monitoring": "Operational Awareness",
    "Reporting": "Reliability Analytics",
}


def canonical_capability(name: str) -> str:
    cleaned = " ".join(str(name or "").split())
    return CAPABILITY_CATEGORY_ALIASES.get(cleaned, cleaned)


def is_system_flow_name(name: str) -> bool:
    return " ".join(str(name or "").split()) in SYSTEM_FLOW_NAMES
