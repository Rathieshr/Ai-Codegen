"""Diagnostics for Engineering Skills."""

from __future__ import annotations

from typing import Any

from .types import EngineeringSkill


class SkillDiagnostics:
    def summarize(
        self,
        installed: list[EngineeringSkill],
        recommended: list[dict[str, Any]] | None = None,
        usage_history: list[dict[str, Any]] | None = None,
        execution_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        recommended = recommended or []
        usage_history = usage_history or []
        execution_history = execution_history or []
        categories: dict[str, int] = {}
        groups: dict[str, int] = {}
        for skill in installed:
            categories[skill.category] = categories.get(skill.category, 0) + 1
            groups[skill.group] = groups.get(skill.group, 0) + 1
        average_confidence = (
            sum(skill.confidence for skill in installed) / len(installed)
            if installed
            else 0.0
        )
        success_count = sum(1 for event in execution_history if event.get("status") == "success")
        failure_count = sum(1 for event in execution_history if event.get("status") != "success")
        success_rate = round((success_count / len(execution_history)) * 100, 2) if execution_history else 0.0
        agent_usage: dict[str, int] = {}
        for event in execution_history:
            agent = str(event.get("agentId") or "manual")
            agent_usage[agent] = agent_usage.get(agent, 0) + 1
        return {
            "installedSkillCount": len(installed),
            "recommendedSkillCount": len(recommended),
            "categories": categories,
            "groups": groups,
            "averageConfidence": round(average_confidence, 3),
            "usageEvents": len(usage_history),
            "executionEvents": len(execution_history),
            "successRate": success_rate,
            "failureCount": failure_count,
            "recentlyUsedSkillIds": _recent_skill_ids(usage_history),
            "agentUsage": agent_usage,
            "dependencies": sorted({dependency for skill in installed for dependency in skill.dependencies}),
            "resolutionMode": "deterministic",
            "llmRequired": False,
        }


def _recent_skill_ids(usage_history: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for entry in reversed(usage_history[-20:]):
        for skill_id in entry.get("skillIds", []) or []:
            if skill_id not in ids:
                ids.append(skill_id)
    return ids[:8]
