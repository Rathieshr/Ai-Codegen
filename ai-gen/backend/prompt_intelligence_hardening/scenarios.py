"""Deterministic repository scenarios for Prompt Intelligence hardening."""

from __future__ import annotations

from typing import Any

from backend.execution import ExecutionPackageBuilder, ExecutionRequest


REPOSITORY_SCENARIOS = (
    {"id": "small-code-indexed", "repositoryMode": "CodeIndexed", "repositorySize": "Small", "fileCount": 4},
    {"id": "large-code-indexed", "repositoryMode": "CodeIndexed", "repositorySize": "Large", "fileCount": 600},
    {"id": "knowledge-snapshot", "repositoryMode": "KnowledgeSnapshot", "repositorySize": "Small", "fileCount": 0},
    {"id": "repository-unavailable", "repositoryMode": "Unavailable", "repositorySize": "Unavailable", "fileCount": 0},
)


def build_execution_package(scenario: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(scenario["id"])
    mode = str(scenario["repositoryMode"])
    file_count = int(scenario["fileCount"])
    selected_context = [
        {
            "sourceType": "Planning",
            "category": "Planning",
            "title": "Review device health",
            "content": "Approved operations story.",
            "confidenceScore": 0.96,
        },
        {
            "sourceType": "Repository",
            "category": "Module",
            "title": "Asset Health",
            "content": "Approved module evidence.",
            "confidenceScore": 0.91 if mode == "CodeIndexed" else 0.76,
        },
        {
            "sourceType": "Repository",
            "category": "Dependency",
            "title": "Telemetry Service",
            "content": "Device health dependency.",
            "confidenceScore": 0.88,
        },
        {
            "sourceType": "EngineeringStandards",
            "category": "Standard",
            "title": "Role-based access",
            "content": "Authorization is required.",
            "confidenceScore": 0.94,
        },
    ]
    if mode == "CodeIndexed":
        selected_context.extend(
            {
                "sourceType": "Repository",
                "category": "File",
                "title": f"src/device-health/DeviceHealthComponent{index:04d}.cs",
                "path": f"src/device-health/DeviceHealthComponent{index:04d}.cs",
                "content": f"Direct repository evidence for device health component {index}.",
                "confidenceScore": round(0.99 - min(index, 500) / 1000, 3),
                "directEvidence": True,
            }
            for index in range(file_count)
        )
    elif mode == "Unavailable":
        selected_context = [item for item in selected_context if item["sourceType"] != "Repository"]

    capsule = {
        "capsuleId": f"capsule-hardening-{scenario_id}",
        "capsuleVersion": "3.5",
        "knowledgeVersion": "knowledge-hardening-v1",
        "planningVersion": "planning-hardening-v1",
        "engineeringMemoryVersion": "memory-hardening-v1",
        "repositorySnapshotVersion": "snapshot-hardening-v1" if mode != "Unavailable" else "",
        "repositoryMode": mode,
        "confidence": 0.94 if mode == "CodeIndexed" else 0.78 if mode == "KnowledgeSnapshot" else 0.62,
        "freshnessStatus": "Fresh" if mode != "Unavailable" else "Unavailable",
        "businessGoal": "Reduce the time required to identify unhealthy field devices.",
        "artifact": {
            "id": f"story-hardening-{scenario_id}",
            "title": "Review device health",
            "description": "Allow an Operations User to review device status and telemetry freshness.",
        },
        "acceptanceCriteria": [
            "Authorized Operations Users can view device health and communication status.",
            "Stale telemetry is identified with its last received timestamp.",
            "Unavailable repository evidence never produces invented file paths.",
        ],
        "selectedCapabilities": ["Device Health Monitoring"],
        "selectedFlows": ["Device Health Review Flow"],
        "selectedStandards": ["Role-based access", "Structured logging", "Input validation"],
        "suggestedTests": ["Permission test", "Stale telemetry test", "Missing telemetry test"],
        "selectedContext": selected_context,
        "warnings": ["Repository unavailable."] if mode == "Unavailable" else [],
        "diagnostics": {"repositoryMode": mode, "repositorySize": scenario["repositorySize"]},
    }
    return ExecutionPackageBuilder().build(
        capsule,
        ExecutionRequest(
            "ImplementationPackage",
            story_id=capsule["artifact"]["id"],
            task_id=f"task-hardening-{scenario_id}",
            repository_snapshot_version=capsule["repositorySnapshotVersion"],
        ),
    )
