"""Engineering Skills orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .composer import SkillComposer
from .context import SkillContext
from .diagnostics import SkillDiagnostics
from .executor import SkillExecutor
from .history import SkillHistory
from .policy import SkillPolicy
from .registry import SkillRegistry
from .resolver import SkillResolver
from .types import EngineeringSkill, now_iso
from .versioning import SkillVersioning


class SkillEngine:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._registry = SkillRegistry(storage_path)
        self._resolver = SkillResolver()
        self._composer = SkillComposer()
        self._versioning = SkillVersioning()
        self._diagnostics = SkillDiagnostics()
        history_path = None
        if storage_path is not None:
            history_path = storage_path.parent / "engineering_skill_history.json"
        self._context = SkillContext()
        self._policy = SkillPolicy()
        self._executor = SkillExecutor()
        self._history = SkillHistory(history_path)

    def dashboard(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        installed = self._registry.list_skills()
        usage = self._registry.usage_history()
        execution_history = self._history.list()
        recommended: list[dict[str, Any]] = []
        if context and isinstance(context.get("execution_package"), dict):
            recommended = self.resolve(context.get("execution_package") or {}, context).get("recommendedSkills", [])
        recent_ids = {skill_id for item in usage[-20:] for skill_id in item.get("skillIds", [])}
        recently_used = [skill.to_dict() for skill in installed if skill.id in recent_ids]
        groups = self._group_skills(installed)
        return {
            "installedSkills": [skill.to_dict() for skill in installed],
            "groupedSkills": groups,
            "recommendedSkills": recommended,
            "recentlyUsed": recently_used[:8],
            "usageHistory": usage[-25:],
            "executionHistory": execution_history[-25:],
            "diagnostics": self._diagnostics.summarize(installed, recommended, usage, execution_history),
        }

    def list_skills(self) -> dict[str, Any]:
        skills = self._registry.list_skills()
        return {
            "skills": [skill.to_dict() for skill in skills],
            "groupedSkills": self._group_skills(skills),
            "count": len(skills),
            "diagnostics": self._diagnostics.summarize(skills, [], self._registry.usage_history(), self._history.list()),
        }

    def save_skill(self, skill_payload: dict[str, Any]) -> dict[str, Any]:
        skill = EngineeringSkill.from_dict(skill_payload)
        if not skill.id:
            skill.id = f"skill_{skill.name.lower().replace(' ', '_')}"
        saved = self._registry.save_skill(skill)
        return saved.to_dict()

    def resolve(self, execution_package: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        skills = self._registry.list_skills()
        memory_context = (context or {}).get("memoryContext") or (context or {}).get("engineeringMemory") or {}
        resolved = self._resolver.resolve(execution_package, skills, memory_context)
        resolved["diagnostics"] = self._diagnostics.summarize(skills, resolved.get("recommendedSkills", []), self._registry.usage_history(), self._history.list())
        return resolved

    def discover(self, agent_id: str, artifact: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        skills = self._registry.list_skills()
        discovery = self._resolver.discover_for_agent(agent_id, artifact, skills, context)
        discovery["diagnostics"] = self._diagnostics.summarize(skills, discovery.get("availableSkills", []), self._registry.usage_history(), self._history.list())
        return discovery

    def compose(self, execution_package: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved = self.resolve(execution_package, context)
        composed = self._composer.compose(resolved.get("recommendedSkills", []), execution_package)
        skill_ids = [str(skill.get("id")) for skill in composed.get("skills", []) if skill.get("id")]
        if skill_ids:
            self._registry.record_usage(skill_ids, {
                "packageId": execution_package.get("packageId", ""),
                "taskId": execution_package.get("taskId", ""),
                "storyId": execution_package.get("storyId", ""),
                "usedAt": now_iso(),
            })
        composed["diagnostics"] = {
            **resolved.get("diagnostics", {}),
            "resolutionReason": resolved.get("resolutionReason", ""),
            "matchCount": resolved.get("matchCount", 0),
        }
        return composed

    def execute(self, skill_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = self._context.build(context)
        skill = self._find_skill(skill_id)
        policy = self._policy.evaluate(skill, normalized)
        if not policy["allowed"]:
            event = {
                "skillId": skill.id,
                "skillName": skill.name,
                "group": skill.group,
                "agentId": normalized.get("agentId", ""),
                "status": "blocked",
                "policy": policy,
                "executedAt": now_iso(),
            }
            self._history.record(event)
            return {"skill": skill.to_dict(), "status": "blocked", "policy": policy, "result": {}}
        result = self._executor.execute(skill, normalized)
        event = {
            "skillId": skill.id,
            "skillName": skill.name,
            "group": skill.group,
            "agentId": normalized.get("agentId", ""),
            "status": result.get("status", "success"),
            "durationMs": result.get("durationMs", 0),
            "executedAt": result.get("executedAt", now_iso()),
            "artifactTitle": result.get("inputSummary", {}).get("artifactTitle", ""),
        }
        self._history.record(event)
        self._registry.record_usage([skill.id], {"usedAt": event["executedAt"], "artifact": normalized.get("artifact", {})})
        return {"skill": skill.to_dict(), "status": "success", "policy": policy, "result": result}

    def version_skill(self, skill_id: str, changes: dict[str, Any] | None = None) -> dict[str, Any]:
        for skill in self._registry.list_skills():
            if skill.id == skill_id:
                updated = self._versioning.version(skill, changes)
                return self._registry.save_skill(updated).to_dict()
        raise ValueError(f"Engineering Skill not found: {skill_id}")

    def diagnostics_summary(self) -> dict[str, Any]:
        return self._diagnostics.summarize(
            self._registry.list_skills(),
            [],
            self._registry.usage_history(),
            self._history.list(),
        )

    def history(self) -> dict[str, Any]:
        events = self._history.list()
        return {"events": events, "count": len(events)}

    def policies(self) -> dict[str, Any]:
        return {
            "rules": [
                "Skills respect governance and approval boundaries.",
                "Skills require matching permissions before execution.",
                "Skills can be blocked by workspace, artifact state, or approval state.",
                "Skills provide guidance and prepared outputs; they do not bypass human control.",
            ],
            "notes": "Skill execution evaluates permissions, workspace, artifact state, and approval rules before running.",
        }

    def _find_skill(self, skill_id: str) -> EngineeringSkill:
        for skill in self._registry.list_skills():
            if skill.id == skill_id:
                return skill
        raise ValueError(f"Engineering Skill not found: {skill_id}")

    def _group_skills(self, skills: list[EngineeringSkill]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for skill in skills:
            grouped.setdefault(skill.group, []).append(skill.to_dict())
        return grouped
