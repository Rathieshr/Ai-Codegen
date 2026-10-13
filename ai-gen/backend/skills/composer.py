"""Compose matched skills into execution guidance."""

from __future__ import annotations

from typing import Any


class SkillComposer:
    def compose(self, recommended_skills: list[dict[str, Any]], execution_package: dict[str, Any]) -> dict[str, Any]:
        skills = recommended_skills[:6]
        return {
            "skills": skills,
            "composition": {
                "compositionSummary": self._summary(skills),
                "implementationGuidance": _collect_unique(skills, "implementationPattern"),
                "repositoryHints": _collect_nested(skills, "repositoryHints"),
                "architectureRules": _collect_nested(skills, "architectureRules"),
                "acceptanceTemplates": _collect_nested(skills, "acceptanceTemplates"),
                "testTemplates": _collect_nested(skills, "testTemplates"),
                "validationRules": _collect_nested(skills, "validationRules"),
                "executionPlanImpact": self._impact(skills, execution_package),
            },
        }

    @staticmethod
    def _summary(skills: list[dict[str, Any]]) -> str:
        if not skills:
            return "No reusable engineering skills were selected."
        return " + ".join(str(skill.get("name") or "Engineering Skill") for skill in skills[:5])

    @staticmethod
    def _impact(skills: list[dict[str, Any]], execution_package: dict[str, Any]) -> str:
        target = (
            execution_package.get("taskId")
            or execution_package.get("sourceWorkItemId")
            or execution_package.get("packageId")
            or "current task"
        )
        if not skills:
            return f"Execution plan for {target} will rely on package-specific guidance only."
        return f"Execution plan for {target} is enriched with {len(skills)} reusable engineering skill(s)."


def _collect_unique(skills: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for skill in skills:
        value = str(skill.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _collect_nested(skills: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for skill in skills:
        for value in skill.get(key, []) or []:
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values
