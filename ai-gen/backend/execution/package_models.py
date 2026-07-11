"""Contracts for the canonical Execution Package v2 pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXECUTION_MODES = {"Implement", "Refactor", "BugFix", "Spike", "POC"}


@dataclass
class ExecutionRequest:
    purpose: str
    story_id: str = ""
    task_id: str = ""
    repository_snapshot_version: str = ""
    branch: str = ""
    target_platform: str = ""
    execution_mode: str = "Implement"
    selected_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    local_workspace_context: dict[str, Any] = field(default_factory=dict)
    developer_preferences: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExecutionRequest":
        return cls(
            purpose=str(value.get("purpose") or "ImplementationPackage"),
            story_id=str(value.get("storyId") or ""), task_id=str(value.get("taskId") or ""),
            repository_snapshot_version=str(value.get("repositorySnapshotVersion") or ""),
            branch=str(value.get("branch") or ""), target_platform=str(value.get("targetPlatform") or ""),
            execution_mode=str(value.get("executionMode") or "Implement"),
            selected_files=[str(item) for item in value.get("selectedFiles", [])],
            changed_files=[str(item) for item in value.get("changedFiles", [])],
            local_workspace_context=dict(value.get("localWorkspaceContext") or {}),
            developer_preferences=dict(value.get("developerPreferences") or {}),
        )

    def validate(self) -> None:
        if not self.purpose: raise ValueError("ExecutionRequest purpose is required.")
        if self.execution_mode not in EXECUTION_MODES:
            raise ValueError(f"Unsupported executionMode '{self.execution_mode}'.")


def normalize_capsule(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy or orchestrator capsules without retrieving any source."""
    capsule = dict(value or {})
    selected = capsule.get("selectedContext") if isinstance(capsule.get("selectedContext"), list) else []
    rejected = capsule.get("rejectedContext") if isinstance(capsule.get("rejectedContext"), list) else []
    sections: dict[str, list[dict[str, Any]]] = {}
    for candidate in selected:
        if not isinstance(candidate, dict): continue
        sections.setdefault(str(candidate.get("sourceType") or "Unknown"), []).append(candidate)
    capsule["contextSections"] = sections
    capsule["rejectedContext"] = rejected
    capsule.setdefault("capsuleId", capsule.get("requestId") or "")
    capsule.setdefault("capsuleVersion", capsule.get("version") or "1")
    capsule.setdefault("confidence", 0.0)
    return capsule
