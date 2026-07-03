"""Skill resolution from execution context."""

from __future__ import annotations

from typing import Any

from .matcher import SkillMatcher
from .types import EngineeringSkill, SkillMatch


class SkillResolver:
    def __init__(self, matcher: SkillMatcher | None = None) -> None:
        self._matcher = matcher or SkillMatcher()

    def resolve(
        self,
        execution_package: dict[str, Any],
        skills: list[EngineeringSkill],
        memory_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        matches = self._matcher.match(execution_package, skills, memory_context)
        return {
            "recommendedSkills": [match.to_dict() for match in matches],
            "matchCount": len(matches),
            "categories": sorted({match.skill.category for match in matches}),
            "resolutionReason": _resolution_reason(matches),
        }

    def discover_for_agent(
        self,
        agent_id: str,
        artifact: dict[str, Any],
        skills: list[EngineeringSkill],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        artifact_type = str(artifact.get("type") or artifact.get("artifactType") or context.get("artifactType") or "").strip()
        agent_matches: list[EngineeringSkill] = []
        for skill in skills:
            if skill.compatible_agents and agent_id not in skill.compatible_agents:
                continue
            if artifact_type and skill.supported_artifacts and artifact_type not in skill.supported_artifacts:
                continue
            agent_matches.append(skill)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for skill in agent_matches:
            grouped.setdefault(skill.group, []).append(skill.to_dict())
        return {
            "agentId": agent_id,
            "artifactType": artifact_type or "Artifact",
            "availableSkills": [skill.to_dict() for skill in agent_matches],
            "groupedSkills": grouped,
            "count": len(agent_matches),
        }


def _resolution_reason(matches: list[SkillMatch]) -> str:
    if not matches:
        return "No engineering skills matched the current execution package."
    names = ", ".join(match.skill.name for match in matches[:3])
    return f"Matched reusable engineering skills from execution package context: {names}."
