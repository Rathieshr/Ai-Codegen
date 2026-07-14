"""Single-contract models for migrated Execution Package consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CONSUMERS = {"DeveloperPrompt", "Validation", "QA", "MemoryCapture", "AgentRuntime", "VSCode"}


@dataclass
class ConsumerRequest:
    consumer: str
    execution_package: dict[str, Any]
    agent_context: dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "Implement"
    runtime_evidence: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""

    def validate(self) -> None:
        if self.consumer not in CONSUMERS: raise ValueError(f"Unsupported Execution Package consumer '{self.consumer}'.")
        if not self.execution_package.get("packageId"): raise ValueError("A persisted Execution Package is required.")


def trace_diagnostics(package: dict[str, Any], *, correlation_id: str, activity_id: str = "", duration_ms: float = 0, warnings: list[str] | None = None) -> dict[str, Any]:
    metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
    diagnostics = package.get("diagnostics") if isinstance(package.get("diagnostics"), dict) else {}
    return {
        "packageId": package.get("packageId") or metadata.get("packageId"),
        "contextCapsuleId": metadata.get("capsuleId") or diagnostics.get("capsuleId"),
        "executionPackageVersion": diagnostics.get("builderVersion") or "2.0",
        "contextCapsuleVersion": metadata.get("capsuleVersion"),
        "repositorySnapshotVersion": metadata.get("repositorySnapshotVersion") or package.get("repositorySnapshotVersion"),
        "knowledgeVersion": metadata.get("knowledgeVersion") or package.get("knowledgeVersion"),
        "engineeringMemoryVersion": metadata.get("engineeringMemoryVersion"),
        "confidence": metadata.get("confidence", diagnostics.get("confidence", 0)),
        "warnings": list(dict.fromkeys([*(diagnostics.get("warnings") or []), *(warnings or [])])),
        "correlationId": correlation_id,
        "activityId": activity_id,
        "durationMs": duration_ms,
    }
