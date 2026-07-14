"""Deterministic Milestone 3.5 regression scenarios."""

SCENARIOS = [
    {
        "scenarioId": "device-health-dashboard",
        "name": "Device Health Dashboard",
        "requirement": "Provide Operations Center users with a unified dashboard showing device health, communication status, battery condition, alarms, and operational risk.",
        "domains": ["Asset Health", "Telemetry", "Operational Awareness", "Alert Management"],
        "acceptanceCriteria": [
            "Operations users can view device health, communication status, battery condition, alarms, and operational risk in one dashboard.",
            "The dashboard displays unavailable telemetry with a clear data-quality state.",
            "Authorized users can filter devices by health status and communication state.",
        ],
    },
    {
        "scenarioId": "alarm-notification-center",
        "name": "Centralized Alarm Notification Center",
        "requirement": "Allow Operations Users to receive, prioritize, acknowledge, filter, and review operational alarms.",
        "domains": ["Alert Management", "Notification Management", "Event Management", "Operational Awareness"],
        "acceptanceCriteria": [
            "Operations users can prioritize and acknowledge active operational alarms.",
            "Authorized users can filter alarms by severity, status, and source.",
            "The system records alarm acknowledgement with user identity and timestamp.",
        ],
    },
    {
        "scenarioId": "user-administration",
        "name": "User Administration",
        "requirement": "Allow administrators to create users, assign roles, disable access, and review audit history.",
        "domains": ["User Management", "Authentication", "Authorization", "Audit"],
        "excludedDomains": ["Firmware", "Telemetry", "Fault Monitoring"],
        "acceptanceCriteria": [
            "Administrators can create a user and assign one or more approved roles.",
            "Administrators can disable user access while preserving audit history.",
            "Authorized administrators can review role and access changes with actor and timestamp.",
        ],
    },
    {
        "scenarioId": "firmware-rollout-management",
        "name": "Firmware Rollout Management",
        "requirement": "Allow operations teams to plan, approve, execute, monitor, pause, and roll back firmware deployments.",
        "domains": ["Firmware Management", "Deployment", "Compliance", "Device Management"],
        "acceptanceCriteria": [
            "Operations teams can plan and approve a firmware deployment before execution.",
            "Authorized operators can pause or roll back an active deployment.",
            "The system records deployment progress and compliance state for each target device.",
        ],
    },
    {
        "scenarioId": "energy-consumption-analytics",
        "name": "Energy Consumption Analytics",
        "requirement": "Provide energy usage trends, comparisons, exports, and abnormal consumption insights.",
        "domains": ["Analytics", "Reporting", "Telemetry", "Trend Analysis"],
        "acceptanceCriteria": [
            "Operations users can compare energy usage across an approved time range.",
            "Authorized users can export the filtered energy usage results.",
            "The analytics view identifies abnormal consumption with the supporting time period and meter context.",
        ],
    },
]


def scenario_by_id(scenario_id: str) -> dict | None:
    return next((dict(item) for item in SCENARIOS if item["scenarioId"] == scenario_id), None)
