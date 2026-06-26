from __future__ import annotations

CORE_CAPABILITIES = [
    "Operational Awareness",
    "Critical Fault Detection",
    "Alert Management",
    "Outage Investigation",
    "Asset Health",
    "Device Health",
    "Telemetry Review",
    "Reporting",
    "Reliability Analytics",
    "Dashboard Monitoring",
    "Notification",
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
        "keywords": ["operation", "operational", "live view", "status", "production health", "equipment status", "monitoring"],
        "modules": ["Fault Monitoring", "Telemetry", "Asset Health"],
        "flows": ["Dashboard Monitoring", "Fault Review", "Telemetry Review"],
    },
    "Critical Fault Detection": {
        "keywords": ["critical fault", "fault event", "fault", "alarm", "outage"],
        "modules": ["Fault Monitoring", "Telemetry"],
        "flows": ["Fault Review", "Alert Review"],
    },
    "Alert Management": {
        "keywords": ["alert", "alarm", "acknowledge", "escalation", "response"],
        "modules": ["Fault Monitoring", "Notification"],
        "flows": ["Alert Review", "Fault Review"],
    },
    "Outage Investigation": {
        "keywords": ["outage", "investigation", "triage", "fault event", "root cause", "event timeline"],
        "modules": ["Fault Monitoring", "Telemetry", "Device Health"],
        "flows": ["Investigation", "Fault Review", "Telemetry Review"],
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
    "Reliability Analytics": {
        "keywords": ["analytics", "trend", "kpi", "metric", "reliability", "analysis"],
        "modules": ["Reporting", "Asset Health", "Telemetry"],
        "flows": ["Analytics Review", "Telemetry Review"],
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
    "Critical Fault Detection": "fault_detection",
    "Asset Health": "asset_health",
    "Device Health": "asset_health",
    "Authentication": "access",
    "Authorization": "access",
    "Firmware Management": "firmware",
    "Device Management": "device",
}
