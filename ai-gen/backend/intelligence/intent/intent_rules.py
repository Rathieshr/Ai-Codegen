from __future__ import annotations

CAPABILITY_RULES: dict[str, list[str]] = {
    "Operational Awareness": ["operation", "operational", "live", "status", "monitor", "dashboard", "visibility", "health"],
    "Alert Management": ["alert", "alarm", "notify", "notification", "acknowledge", "critical", "warning"],
    "Investigation": ["investigate", "investigation", "outage", "triage", "root cause", "correlate", "timeline"],
    "Reporting": ["report", "export", "summary", "audit", "evidence"],
    "Analytics": ["analytics", "trend", "kpi", "metric", "insight", "forecast"],
    "Asset Health": ["asset", "device health", "condition", "fleet", "recloser"],
    "Notification": ["notify", "notification", "message", "subscription", "email", "sms"],
    "Dashboard": ["dashboard", "workspace", "view", "screen", "panel"],
    "Telemetry": ["telemetry", "signal", "reading", "meter", "sensor", "freshness"],
    "Authentication": ["login", "sign in", "authentication", "authorization", "token", "session", "otp", "password"],
    "Firmware": ["firmware", "upgrade", "rollout", "rollback", "version", "device update"],
}

DOMAIN_RULES: dict[str, list[str]] = {
    "Operations": ["operation", "operator", "dashboard", "monitor", "alert", "alarm"],
    "Production": ["production", "release", "deploy", "availability", "uptime"],
    "Distribution": ["distribution", "grid", "feeder", "outage", "fault"],
    "Asset Management": ["asset", "device", "recloser", "health", "fleet"],
    "Field Service": ["field", "technician", "work order", "dispatch", "crew"],
    "Telemetry": ["telemetry", "meter", "reading", "signal", "sensor"],
    "Firmware": ["firmware", "version", "upgrade", "rollout", "rollback"],
    "Security": ["security", "permission", "role", "access", "unauthorized"],
    "Authentication": ["login", "authentication", "authorization", "token", "session", "otp"],
}

PERSONA_RULES: dict[str, list[str]] = {
    "Operations User": ["operations user", "operator", "operations team", "operations analyst"],
    "Supervisor": ["supervisor", "manager", "lead", "operations manager"],
    "Field Technician": ["field technician", "technician", "field user", "crew"],
    "Administrator": ["administrator", "admin", "system administrator"],
    "Customer": ["customer", "end user", "consumer"],
    "Product Owner": ["product owner", "stakeholder", "business owner"],
}

ACTION_RULES: dict[str, list[str]] = {
    "Monitor": ["monitor", "watch", "track", "observe"],
    "Review": ["review", "view", "inspect", "open", "see"],
    "Investigate": ["investigate", "triage", "diagnose", "correlate"],
    "Generate": ["generate", "create", "produce"],
    "Approve": ["approve", "accept", "authorize"],
    "Filter": ["filter", "sort", "search"],
    "Export": ["export", "download"],
    "Update": ["update", "edit", "modify"],
    "Create": ["create", "add", "start"],
    "Delete": ["delete", "remove"],
    "Acknowledge": ["acknowledge", "ack", "dismiss"],
}

ENTITY_RULES: dict[str, list[str]] = {
    "Device": ["device", "meter", "recloser", "asset"],
    "Event": ["event", "incident"],
    "Fault": ["fault", "failure"],
    "Alert": ["alert", "alarm", "notification"],
    "Telemetry": ["telemetry", "signal", "reading"],
    "Investigation": ["investigation", "triage", "root cause"],
    "Dashboard": ["dashboard", "workspace", "screen"],
    "Operator": ["operator", "operations user"],
    "Work Order": ["work order", "dispatch", "crew"],
    "Asset": ["asset", "device health"],
    "User Account": ["login", "user", "account", "token", "session"],
    "Firmware": ["firmware", "version", "rollout", "rollback"],
}

TECHNICAL_KEYWORDS = [
    "REST",
    "BLE",
    "Telemetry",
    "Azure",
    "Authentication",
    "Authorization",
    "API",
    "Firmware",
    "Mobile",
    "Database",
    "Backend",
    "Frontend",
    "MQTT",
    "JWT",
    "OAuth2",
    "MAUI",
]

MODULE_HINTS: dict[str, list[str]] = {
    "Fault Monitoring": ["fault", "outage", "event", "critical", "alarm"],
    "Telemetry": ["telemetry", "signal", "reading", "freshness", "meter"],
    "Dashboard": ["dashboard", "workspace", "visibility", "view", "screen"],
    "Reporting": ["report", "export", "audit", "summary"],
    "Authentication": ["login", "authentication", "authorization", "token", "session", "otp", "password"],
    "Firmware": ["firmware", "upgrade", "rollout", "rollback", "version"],
    "Asset Health": ["asset", "device health", "condition", "recloser"],
    "Notification": ["alert", "notify", "notification", "message"],
}

FLOW_HINTS: dict[str, list[str]] = {
    "Fault Review": ["fault", "event", "review", "critical"],
    "Investigation": ["investigation", "outage", "triage", "root cause"],
    "Alert Review": ["alert", "alarm", "acknowledge", "notification"],
    "Dashboard Monitoring": ["dashboard", "monitor", "visibility", "status"],
    "Telemetry Review": ["telemetry", "reading", "signal", "freshness"],
    "Authentication": ["login", "authentication", "otp", "password"],
    "Token Refresh": ["token", "session", "refresh"],
    "Firmware Rollout": ["firmware", "rollout", "upgrade", "rollback"],
}

STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "be",
    "by",
    "for",
    "from",
    "i",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "to",
    "with",
    "want",
    "wants",
    "can",
    "should",
}

