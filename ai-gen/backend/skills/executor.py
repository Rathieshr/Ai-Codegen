"""Skill execution for Engineering Skills."""

from __future__ import annotations

import time
from typing import Any

from .types import EngineeringSkill, now_iso


class SkillExecutor:
    def execute(self, skill: EngineeringSkill, context: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        artifact = context.get("artifact", {})
        execution_context = context.get("executionContext", {})
        planning_context = context.get("planningContext", {})
        knowledge = context.get("knowledgeRegistry", {})
        repository = context.get("repositoryIntelligence", {})
        memory = context.get("engineeringMemory", {})

        result = {
            "skillId": skill.id,
            "skillName": skill.name,
            "status": "success",
            "executedAt": now_iso(),
            "durationMs": round((time.monotonic() - started) * 1000, 2),
            "inputSummary": {
                "artifactTitle": artifact.get("title") or artifact.get("name") or execution_context.get("title") or planning_context.get("title") or "",
                "workspace": context.get("workspace", ""),
                "agentId": context.get("agentId", ""),
            },
            "output": self._build_output(skill, artifact, execution_context, planning_context, knowledge, repository, memory),
        }
        result["durationMs"] = round((time.monotonic() - started) * 1000, 2)
        return result

    def _build_output(
        self,
        skill: EngineeringSkill,
        artifact: dict[str, Any],
        execution_context: dict[str, Any],
        planning_context: dict[str, Any],
        knowledge: dict[str, Any],
        repository: dict[str, Any],
        memory: dict[str, Any],
    ) -> dict[str, Any]:
        title = str(artifact.get("title") or execution_context.get("title") or planning_context.get("title") or skill.name).strip()
        modules = _names(knowledge.get("modules") or repository.get("modules") or execution_context.get("affectedModules") or [])
        flows = _names(knowledge.get("flows") or repository.get("flows") or execution_context.get("affectedFlows") or [])
        files = _names(repository.get("rankedFiles") or repository.get("relevantFiles") or execution_context.get("relevantFiles") or [])
        memories = memory.get("relevantMemories") if isinstance(memory.get("relevantMemories"), list) else []

        return {
            "summary": f"{skill.name} prepared guidance for {title or 'the current artifact'}.",
            "implementationPattern": skill.implementation_pattern,
            "repositoryHints": skill.repository_hints[:6],
            "acceptanceTemplates": skill.acceptance_templates[:5],
            "testTemplates": skill.test_templates[:5],
            "validationRules": skill.validation_rules[:5],
            "selectedModules": modules[:6],
            "selectedFlows": flows[:6],
            "selectedFiles": files[:6],
            "memoryReferences": [str(item.get('title') or 'Engineering Memory') for item in memories[:4] if isinstance(item, dict)],
        }


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("path") or item.get("title") or "").strip()
        else:
            name = str(item).strip()
        if name and name not in names:
            names.append(name)
    return names
