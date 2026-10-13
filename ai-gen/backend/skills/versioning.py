"""Skill version management."""

from __future__ import annotations

from typing import Any

from .types import EngineeringSkill


class SkillVersioning:
    def version(self, skill: EngineeringSkill, changes: dict[str, Any] | None = None) -> EngineeringSkill:
        changes = changes or {}
        updated = skill.to_dict()
        updated.update(changes)
        updated["version"] = skill.version + 1
        return EngineeringSkill.from_dict(updated)
