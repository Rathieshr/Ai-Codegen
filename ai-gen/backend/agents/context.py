"""Agent context normalization helpers."""

from __future__ import annotations

from typing import Any

from .types import clean


class AgentContext:
    def normalize(self, context: dict[str, Any] | None) -> dict[str, Any]:
        context = context or {}
        execution_package = context.get("executionPackage") if isinstance(context.get("executionPackage"), dict) else {}
        return {
            "projectId": clean(context.get("projectId") or context.get("project_id") or "default"),
            "repository": clean(context.get("repository")),
            "branch": clean(context.get("branch")),
            "module": clean(context.get("module")),
            "capability": clean(context.get("capability")),
            "workItem": context.get("workItem") if isinstance(context.get("workItem"), dict) else {},
            "parent": context.get("parent") if isinstance(context.get("parent"), dict) else {},
            "executionPackage": execution_package,
            "executionMode": clean(context.get("executionMode") or "Implement"),
            "agentContext": context.get("agentContext") if isinstance(context.get("agentContext"), dict) else {},
            # Deprecated compatibility aliases, projected only from the package.
            "memoryContext": execution_package.get("engineeringMemory") if isinstance(execution_package.get("engineeringMemory"), dict) else {},
            "repositoryContext": execution_package.get("repositoryContext") if isinstance(execution_package.get("repositoryContext"), dict) else {},
            "repositorySnapshot": {"version": execution_package.get("repositorySnapshotVersion")},
            "approvalRequired": context.get("approvalRequired", True) is not False,
        }
