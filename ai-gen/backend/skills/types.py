"""Engineering Skill data models for HEI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class EngineeringSkill:
    id: str
    name: str
    category: str
    description: str
    group: str = "Execution"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    supported_artifacts: list[str] = field(default_factory=list)
    required_context: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    compatible_agents: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    implementation_pattern: str = ""
    repository_hints: list[str] = field(default_factory=list)
    architecture_rules: list[str] = field(default_factory=list)
    acceptance_templates: list[str] = field(default_factory=list)
    test_templates: list[str] = field(default_factory=list)
    validation_rules: list[str] = field(default_factory=list)
    match_keywords: list[str] = field(default_factory=list)
    confidence: float = 0.8
    version: int = 1
    usage_count: int = 0
    last_used_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "group": self.group,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "supportedArtifacts": self.supported_artifacts,
            "requiredContext": self.required_context,
            "requiredPermissions": self.required_permissions,
            "compatibleAgents": self.compatible_agents,
            "dependencies": self.dependencies,
            "implementationPattern": self.implementation_pattern,
            "repositoryHints": self.repository_hints,
            "architectureRules": self.architecture_rules,
            "acceptanceTemplates": self.acceptance_templates,
            "testTemplates": self.test_templates,
            "validationRules": self.validation_rules,
            "matchKeywords": self.match_keywords,
            "confidence": round(self.confidence, 3),
            "version": self.version,
            "usageCount": self.usage_count,
            "lastUsedAt": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EngineeringSkill":
        return cls(
            id=str(data.get("id") or "").strip(),
            name=str(data.get("name") or "").strip(),
            category=str(data.get("category") or "").strip() or "Architecture",
            group=str(data.get("group") or "").strip() or "Execution",
            description=str(data.get("description") or "").strip(),
            input_schema=data.get("inputSchema") if isinstance(data.get("inputSchema"), dict) else {},
            output_schema=data.get("outputSchema") if isinstance(data.get("outputSchema"), dict) else {},
            supported_artifacts=_as_list(data.get("supportedArtifacts") or data.get("supported_artifacts")),
            required_context=_as_list(data.get("requiredContext") or data.get("required_context")),
            required_permissions=_as_list(data.get("requiredPermissions") or data.get("required_permissions")),
            compatible_agents=_as_list(data.get("compatibleAgents") or data.get("compatible_agents")),
            dependencies=_as_list(data.get("dependencies")),
            implementation_pattern=str(data.get("implementationPattern") or data.get("implementation_pattern") or "").strip(),
            repository_hints=_as_list(data.get("repositoryHints") or data.get("repository_hints")),
            architecture_rules=_as_list(data.get("architectureRules") or data.get("architecture_rules")),
            acceptance_templates=_as_list(data.get("acceptanceTemplates") or data.get("acceptance_templates")),
            test_templates=_as_list(data.get("testTemplates") or data.get("test_templates")),
            validation_rules=_as_list(data.get("validationRules") or data.get("validation_rules")),
            match_keywords=_as_list(data.get("matchKeywords") or data.get("match_keywords")),
            confidence=_as_float(data.get("confidence"), 0.8),
            version=max(1, int(_as_float(data.get("version"), 1))),
            usage_count=max(0, int(_as_float(data.get("usageCount") or data.get("usage_count"), 0))),
            last_used_at=str(data.get("lastUsedAt") or data.get("last_used_at") or ""),
        )


@dataclass
class SkillMatch:
    skill: EngineeringSkill
    match_score: float
    match_reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = self.skill.to_dict()
        payload["matchScore"] = round(self.match_score, 3)
        payload["matchReasons"] = self.match_reasons
        payload["evidence"] = self.evidence
        return payload


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
