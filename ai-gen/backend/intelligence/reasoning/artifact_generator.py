from __future__ import annotations

import json
from typing import Any

from .duplicate_analyzer import DuplicateAnalyzer
from .planning_artifact import PlanningArtifact, PlanningEvidence
from .prompt_builder import planning_evidence


class ArtifactGenerator:
    def __init__(self) -> None:
        self.duplicates = DuplicateAnalyzer()

    def generate(
        self,
        planning_context: dict[str, Any],
        output_type: str,
        provider_payload: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        raw_artifacts = _provider_artifacts(provider_payload) if provider_payload else []
        if not raw_artifacts:
            raw_artifacts = _deterministic_artifacts(planning_context, output_type)
        evidence = _evidence(planning_context)
        allowed = planning_evidence(planning_context)
        artifacts: list[dict[str, Any]] = []
        for raw in raw_artifacts:
            sanitized, item_warnings = _sanitize(raw, planning_context, output_type, allowed)
            warnings.extend(item_warnings)
            duplicate = self.duplicates.find_duplicate(
                sanitized["title"],
                sanitized["description"],
                _existing_children(planning_context),
            )
            artifact_type = _artifact_type(output_type)
            if duplicate:
                artifact_type = "Duplicate Candidate"
                warnings.append(f"Duplicate candidate detected for {sanitized['title']}.")
            artifact = PlanningArtifact(
                title=("Duplicate Candidate: " + sanitized["title"]) if duplicate else sanitized["title"],
                description=sanitized["description"],
                business_value=sanitized["businessValue"],
                acceptance_criteria=sanitized["acceptanceCriteria"],
                personas=sanitized["personas"],
                dependencies=sanitized["dependencies"],
                risks=sanitized["risks"],
                assumptions=sanitized["assumptions"],
                generated_using=evidence,
                confidence=sanitized["confidence"],
                artifact_type=artifact_type,
                duplicate_candidate=duplicate,
                suggested_capability=sanitized.get("suggestedCapability"),
            ).to_dict()
            artifacts.append(artifact)
        return artifacts, warnings


def _provider_artifacts(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    artifacts = payload.get("artifacts") or payload.get("planningArtifacts")
    if isinstance(artifacts, list):
        return [item for item in artifacts if isinstance(item, dict)]
    if any(key in payload for key in ["title", "description", "businessValue", "acceptanceCriteria"]):
        return [payload]
    return []


def _deterministic_artifacts(planning_context: dict[str, Any], output_type: str) -> list[dict[str, Any]]:
    normalized = _normalize_output_type(output_type)
    capabilities = _names(planning_context.get("selectedCapabilities"))
    modules = _names(planning_context.get("selectedModules"))
    flows = _names(planning_context.get("selectedFlows"))
    personas = _personas(planning_context)
    if normalized.startswith("Feature"):
        selected = capabilities[:4] or ["Operational Awareness"]
        return [_feature_artifact(capability, planning_context, modules, flows, personas) for capability in selected]
    if normalized.startswith("Story"):
        selected = _story_titles(planning_context, capabilities, flows)
        return [_story_artifact(title, planning_context, modules, flows, personas) for title in selected]
    if normalized.startswith("Task"):
        selected = _task_titles(planning_context, modules, flows)
        return [_task_artifact(title, planning_context, modules, flows, personas) for title in selected]
    return [_epic_artifact(planning_context, capabilities, modules, flows, personas)]


def _feature_artifact(capability: str, context: dict[str, Any], modules: list[str], flows: list[str], personas: list[str]) -> dict[str, Any]:
    return {
        "title": capability,
        "description": f"Deliver {capability} as a product capability for {', '.join(personas) or 'users'} using selected modules {', '.join(modules[:3]) or 'approved modules'} and flows {', '.join(flows[:2]) or 'approved flows'}.",
        "businessValue": f"Improves {context.get('expectedOutcome') or context.get('businessGoal') or capability}.",
        "acceptanceCriteria": [
            f"{capability} has a distinct business outcome and does not overlap with another generated feature.",
            f"Behavior is traceable to selected capability context: {capability}.",
            "Stakeholders can review success criteria before story generation.",
        ],
        "personas": personas,
        "dependencies": _names(context.get("selectedDependencies"))[:4],
        "risks": _list(context.get("risks")),
        "assumptions": ["Feature scope remains within the supplied PlanningContext."],
        "confidence": _confidence(context),
    }


def _story_artifact(title: str, context: dict[str, Any], modules: list[str], flows: list[str], personas: list[str]) -> dict[str, Any]:
    persona = personas[0] if personas else "User"
    return {
        "title": title,
        "description": f"As a {persona}, I want to {title[0].lower() + title[1:] if title else 'complete the approved behavior'} so that {context.get('expectedOutcome') or context.get('businessGoal')}.",
        "businessValue": f"Creates independently testable value for {context.get('userProblem') or persona}.",
        "acceptanceCriteria": [
            f"{persona} can complete {title.lower()} using the approved feature intent.",
            f"Behavior is validated against selected flows: {', '.join(flows[:2]) or 'approved flows'}.",
            f"Data and behavior remain within selected modules: {', '.join(modules[:3]) or 'approved modules'}.",
        ],
        "personas": personas,
        "dependencies": _names(context.get("selectedDependencies"))[:4],
        "risks": _list(context.get("risks")),
        "assumptions": ["Story derives from selected feature intent and PlanningContext only."],
        "confidence": _confidence(context),
    }


def _task_artifact(title: str, context: dict[str, Any], modules: list[str], flows: list[str], personas: list[str]) -> dict[str, Any]:
    return {
        "title": title,
        "description": f"Complete the implementation work for {title.lower()} within selected modules {', '.join(modules[:3]) or 'approved modules'} and flows {', '.join(flows[:2]) or 'approved flows'}.",
        "businessValue": "Enables the approved story acceptance criteria to be delivered and validated.",
        "acceptanceCriteria": [
            "Task maps to at least one approved story acceptance criterion.",
            "Implementation stays within selected modules and flows.",
            "No unrelated technical work or repository files are introduced.",
        ],
        "personas": personas,
        "dependencies": _names(context.get("selectedDependencies"))[:4],
        "risks": _list(context.get("risks")),
        "assumptions": ["Repository files are used only when supplied by PlanningContext."],
        "confidence": _confidence(context),
    }


def _epic_artifact(context: dict[str, Any], capabilities: list[str], modules: list[str], flows: list[str], personas: list[str]) -> dict[str, Any]:
    return {
        "title": _title_from_goal(context.get("businessGoal")) or "Refined Epic",
        "description": f"{context.get('businessGoal') or 'Refine the epic'} Scope is constrained to capabilities {', '.join(capabilities[:4]) or 'approved capabilities'}, modules {', '.join(modules[:3]) or 'approved modules'}, and flows {', '.join(flows[:3]) or 'approved flows'}.",
        "businessValue": context.get("expectedOutcome") or context.get("businessGoal") or "Improved business outcome.",
        "acceptanceCriteria": [
            "Business outcome, scope, and success metrics are reviewable.",
            "No implementation detail is introduced during epic refinement.",
            "Feature generation can proceed from selected capabilities.",
        ],
        "personas": personas,
        "dependencies": _names(context.get("selectedDependencies"))[:4],
        "risks": _list(context.get("risks")),
        "assumptions": ["Epic refinement is constrained to PlanningContext."],
        "confidence": _confidence(context),
    }


def _sanitize(raw: dict[str, Any], context: dict[str, Any], output_type: str, allowed: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    text = json.dumps(raw, ensure_ascii=True)
    allowed_terms = set()
    for key in ["capabilities", "modules", "flows", "applications", "standards"]:
        allowed_terms.update(str(item).lower() for item in allowed.get(key, []))
    for rejected in context.get("rejectedContext", []) or []:
        if isinstance(rejected, dict):
            name = str(rejected.get("name") or "")
            if name and name.lower() in text.lower() and name.lower() not in allowed_terms:
                warnings.append(f"Removed rejected context reference: {name}.")
                text = text.replace(name, "")
    try:
        cleaned = json.loads(text)
    except json.JSONDecodeError:
        cleaned = raw
    artifact = {
        "title": _clean(cleaned.get("title")) or _fallback_title(output_type),
        "description": _clean(cleaned.get("description")) or _clean(context.get("businessGoal")) or _fallback_title(output_type),
        "businessValue": _clean(cleaned.get("businessValue") or cleaned.get("business_value")) or _clean(context.get("expectedOutcome")) or "Business value remains traceable to PlanningContext.",
        "acceptanceCriteria": _string_list(cleaned.get("acceptanceCriteria") or cleaned.get("acceptance_criteria"))[:8],
        "personas": _string_list(cleaned.get("personas")) or _personas(context),
        "dependencies": _filter_allowed(_string_list(cleaned.get("dependencies")), _names(context.get("selectedDependencies"))),
        "risks": _string_list(cleaned.get("risks")) or _list(context.get("risks")),
        "assumptions": _string_list(cleaned.get("assumptions")) or ["Human review required before approval."],
        "confidence": min(float(cleaned.get("confidence", _confidence(context)) or _confidence(context)), _confidence(context)),
    }
    if not artifact["acceptanceCriteria"]:
        artifact["acceptanceCriteria"] = _default_acceptance(output_type, context)
    suggested = _clean(cleaned.get("suggestedCapability") or cleaned.get("suggested_capability"))
    if suggested:
        artifact["suggestedCapability"] = suggested
    return artifact, warnings


def _evidence(context: dict[str, Any]) -> PlanningEvidence:
    evidence = planning_evidence(context)
    return PlanningEvidence(
        planning_context_version=str(evidence["planningContextVersion"]),
        capabilities=list(evidence["capabilities"]),
        modules=list(evidence["modules"]),
        flows=list(evidence["flows"]),
        applications=list(evidence["applications"]),
        standards=list(evidence["standards"]),
    )


def _story_titles(context: dict[str, Any], capabilities: list[str], flows: list[str]) -> list[str]:
    base = flows[:3] or capabilities[:3] or ["approved behavior"]
    return [f"{_verb_for(value)} {value}" for value in base][:5]


def _task_titles(context: dict[str, Any], modules: list[str], flows: list[str]) -> list[str]:
    selected = modules[:3] or flows[:3] or ["approved behavior"]
    return [f"Build {value} delivery behavior" for value in selected][:5]


def _verb_for(value: str) -> str:
    text = value.lower()
    if "investigation" in text:
        return "Start"
    if "review" in text:
        return "Review"
    if "dashboard" in text:
        return "View"
    if "alert" in text:
        return "Acknowledge"
    return "Use"


def _default_acceptance(output_type: str, context: dict[str, Any]) -> list[str]:
    normalized = _normalize_output_type(output_type)
    if normalized.startswith("Task"):
        return ["Task maps to approved story acceptance criteria.", "Task remains inside selected modules and flows."]
    if normalized.startswith("Story"):
        return ["Story is independently testable.", "Story derives from selected feature intent."]
    return ["Artifact is traceable to selected PlanningContext.", "Artifact is reviewable before approval."]


def _filter_allowed(values: list[str], allowed: list[str]) -> list[str]:
    if not values:
        return allowed[:4]
    if not allowed:
        return values[:4]
    allowed_lower = {item.lower() for item in allowed}
    return [item for item in values if item.lower() in allowed_lower][:4] or allowed[:4]


def _existing_children(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in context.get("existingChildren", []) if isinstance(item, dict)]


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        name = _clean(item.get("name")) if isinstance(item, dict) else _clean(item)
        if name and name not in output:
            output.append(name)
    return output


def _personas(context: dict[str, Any]) -> list[str]:
    problem = _clean(context.get("userProblem"))
    if "Operations User" in problem or "operator" in problem.lower():
        return ["Operations User"]
    if "technician" in problem.lower():
        return ["Field Technician"]
    return ["User"]


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str) and value:
        return [_clean(value)]
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str):
        return [_clean(item) for item in value.replace("\n", "|").split("|") if _clean(item)]
    return []


def _confidence(context: dict[str, Any]) -> float:
    return round(max(0.35, min(float(context.get("confidence", 0.65) or 0.65), 0.93)), 2)


def _artifact_type(output_type: str) -> str:
    normalized = _normalize_output_type(output_type)
    if normalized.startswith("Feature"):
        return "Feature Recommendation"
    if normalized.startswith("Story"):
        return "Story Recommendation"
    if normalized.startswith("Task"):
        return "Task Recommendation"
    return "Epic Refinement"


def _fallback_title(output_type: str) -> str:
    return _artifact_type(output_type)


def _normalize_output_type(output_type: str) -> str:
    return "".join(part.capitalize() for part in str(output_type or "").replace("_", " ").replace("-", " ").split())


def _title_from_goal(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    return text[:80].rstrip(".")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_clean(item) for item in value if _clean(item))
    return " ".join(str(value).strip().split())

