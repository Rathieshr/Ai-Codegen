from __future__ import annotations

import json
from typing import Any

from .role_resolver import resolve_objective, resolve_role

PROMPT_SECTIONS = [
    "Role",
    "Planning Objective",
    "Business Goal",
    "User Problem",
    "Expected Outcome",
    "Capabilities",
    "Relevant Modules",
    "Relevant Flows",
    "Relevant Applications",
    "Relevant Standards",
    "Constraints",
    "Risks",
    "Generation Rules",
]


class PromptBuilder:
    def build(self, planning_context: dict[str, Any], output_type: str) -> str:
        evidence = planning_evidence(planning_context)
        rules = _generation_rules(output_type)
        sections = [
            ("Role", resolve_role(output_type)),
            ("Planning Objective", resolve_objective(output_type)),
            ("Business Goal", _clean(planning_context.get("businessGoal"))),
            ("User Problem", _clean(planning_context.get("userProblem"))),
            ("Expected Outcome", _clean(planning_context.get("expectedOutcome"))),
            ("Capabilities", _compact_json(evidence["capabilities"])),
            ("Relevant Modules", _compact_json(evidence["modules"])),
            ("Relevant Flows", _compact_json(evidence["flows"])),
            ("Relevant Applications", _compact_json(evidence["applications"])),
            ("Relevant Standards", _compact_json(evidence["standards"])),
            ("Constraints", _compact_json(_list(planning_context.get("constraints")))),
            ("Risks", _compact_json(_list(planning_context.get("risks")))),
            ("Generation Rules", _compact_json(rules)),
        ]
        return "\n\n".join(f"## {heading}\n{body or 'Not specified'}" for heading, body in sections)


def planning_evidence(planning_context: dict[str, Any]) -> dict[str, list[str] | str]:
    return {
        "planningContextVersion": _context_version(planning_context),
        "capabilities": _names(planning_context.get("selectedCapabilities")),
        "modules": _names(planning_context.get("selectedModules")),
        "flows": _names(planning_context.get("selectedFlows")),
        "applications": _names(planning_context.get("selectedApplications")),
        "standards": _names(planning_context.get("selectedStandards")),
    }


def _generation_rules(output_type: str) -> list[str]:
    normalized = "".join(part.capitalize() for part in str(output_type or "").replace("_", " ").split())
    base = [
        "Return ONLY valid JSON.",
        "Do not include markdown, explanations, prose, code fences, or extra text.",
        'If unable to produce the requested artifact, return {"error":"..."} as valid JSON.',
        "Use only the supplied PlanningContext sections.",
        "Do not invent modules, flows, applications, dependencies, standards, or repository files.",
        "If additional capability is needed, return suggestedCapability instead of pretending it exists.",
        "Set validationStatus to Pending.",
    ]
    if normalized.startswith("Feature"):
        return [
            *base,
            "Generate product capabilities, not UI pages.",
            "Each feature must solve exactly one capability and avoid overlap.",
            "Include capability title, capability description, business value, and acceptance criteria.",
        ]
    if normalized.startswith("Story"):
        return [
            *base,
            "Generate independent, valuable, testable user stories.",
            "Acceptance criteria must derive from feature intent.",
            "Include assumptions when context is incomplete.",
        ]
    if normalized.startswith("Task"):
        return [
            *base,
            "Generate implementation tasks only. No code.",
            "Tasks must map to story acceptance criteria and selected modules or flows.",
            "Do not reference repository files unless they are present in PlanningContext.",
        ]
    return [
        *base,
        "Improve business outcome, business value, scope, and success metrics.",
        "Do not introduce implementation details.",
    ]


def _context_version(planning_context: dict[str, Any]) -> str:
    generated_at = _clean(planning_context.get("generatedAt"))
    token_estimate = _clean(planning_context.get("tokenEstimate"))
    return f"planning-context:{generated_at or 'unknown'}:{token_estimate or '0'}"


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = _clean(item.get("name"))
        else:
            name = _clean(item)
        if name and name not in output:
            output.append(name)
    return output


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str):
        return [_clean(item) for item in value.splitlines() if _clean(item)]
    return []


def _compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())
