"""Policy checks for Engineering Skills."""

from __future__ import annotations

from typing import Any

from .types import EngineeringSkill


class SkillPolicy:
    def evaluate(self, skill: EngineeringSkill, context: dict[str, Any]) -> dict[str, Any]:
        permissions = {str(item).strip() for item in context.get("permissions", [])}
        workspace = str(context.get("workspace") or "").strip().lower()
        artifact_state = str(context.get("artifactState") or "").strip().lower()
        approval_state = str(context.get("approvalState") or "").strip().lower()
        reasons: list[str] = []
        allowed = True

        if skill.required_permissions:
            missing = [item for item in skill.required_permissions if item not in permissions]
            if missing:
                allowed = False
                reasons.append(f"missing permissions: {', '.join(missing)}")

        if workspace and skill.category.lower() == "qa" and workspace != "qa":
            reasons.append("QA skill is being used outside QA workspace.")
        if artifact_state in {"closed", "archived"}:
            allowed = False
            reasons.append(f"artifact state blocks execution: {artifact_state}")
        if approval_state in {"rejected", "blocked"}:
            allowed = False
            reasons.append(f"approval state blocks execution: {approval_state}")

        return {
            "allowed": allowed,
            "reasons": reasons or ["allowed by current governance and workspace policy"],
            "workspace": workspace or "unspecified",
            "artifactState": artifact_state or "unspecified",
            "approvalState": approval_state or "unspecified",
        }
