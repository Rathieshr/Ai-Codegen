"""Build the normalized context passed into Engineering Skills."""

from __future__ import annotations

from typing import Any


class SkillContext:
    def build(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        return {
            "repositoryIntelligence": context.get("repositoryIntelligence") if isinstance(context.get("repositoryIntelligence"), dict) else {},
            "knowledgeRegistry": context.get("knowledgeRegistry") if isinstance(context.get("knowledgeRegistry"), dict) else {},
            "engineeringMemory": context.get("engineeringMemory") if isinstance(context.get("engineeringMemory"), dict) else context.get("memoryContext") if isinstance(context.get("memoryContext"), dict) else {},
            "engineeringGraph": context.get("engineeringGraph") if isinstance(context.get("engineeringGraph"), dict) else {},
            "executionContext": context.get("executionContext") if isinstance(context.get("executionContext"), dict) else {},
            "planningContext": context.get("planningContext") if isinstance(context.get("planningContext"), dict) else {},
            "userContext": context.get("userContext") if isinstance(context.get("userContext"), dict) else {},
            "policyContext": context.get("policyContext") if isinstance(context.get("policyContext"), dict) else {},
            "artifact": context.get("artifact") if isinstance(context.get("artifact"), dict) else {},
            "agentId": str(context.get("agentId") or context.get("agent") or "").strip(),
            "workspace": str(context.get("workspace") or "").strip(),
            "artifactState": str(context.get("artifactState") or "").strip(),
            "approvalState": str(context.get("approvalState") or "").strip(),
            "permissions": [str(item).strip() for item in (context.get("permissions") or []) if str(item).strip()],
        }
