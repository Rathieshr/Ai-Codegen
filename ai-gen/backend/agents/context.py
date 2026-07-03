"""Agent context normalization helpers."""

from __future__ import annotations

from typing import Any

from .types import clean


class AgentContext:
    def normalize(self, context: dict[str, Any] | None) -> dict[str, Any]:
        context = context or {}
        return {
            "projectId": clean(context.get("projectId") or context.get("project_id") or "default"),
            "repository": clean(context.get("repository")),
            "branch": clean(context.get("branch")),
            "module": clean(context.get("module")),
            "capability": clean(context.get("capability")),
            "workItem": context.get("workItem") if isinstance(context.get("workItem"), dict) else {},
            "parent": context.get("parent") if isinstance(context.get("parent"), dict) else {},
            "memoryContext": context.get("memoryContext") if isinstance(context.get("memoryContext"), dict) else {},
            "repositoryContext": context.get("repositoryContext") if isinstance(context.get("repositoryContext"), dict) else {},
            "repositorySnapshot": context.get("repositorySnapshot") if isinstance(context.get("repositorySnapshot"), dict) else {},
            "approvalRequired": context.get("approvalRequired", True) is not False,
        }
