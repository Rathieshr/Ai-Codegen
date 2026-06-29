from __future__ import annotations

from typing import Any

from backend.intelligence.capability import buildCapabilityContext
from backend.intelligence.intent import build_intent

from .planning_context import ExistingArtifactSummary, PlanningContext
from .planning_context_selector import PlanningContextSelector
from .planning_diagnostics import build_diagnostics
from .planning_duplicate_detector import PlanningDuplicateDetector, summarize_existing_children
from .planning_lineage import build_lineage
from .planning_role_resolver import resolve_generation_role
from .planning_token_estimator import estimate_tokens


class PlanningContextBuilder:
    def __init__(self) -> None:
        self.selector = PlanningContextSelector()
        self.duplicate_detector = PlanningDuplicateDetector()

    def build(self, work_item: dict[str, Any], parent_work_item: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        work_item = work_item or {}
        parent_work_item = parent_work_item or None
        intent_model = _intent_model(work_item, options)
        project_profile = _dict_option(options, "projectProfile", "project_profile")
        repository_snapshot = _dict_option(options, "repositorySnapshot", "repository_snapshot")
        knowledge_registry = _dict_option(options, "knowledgeRegistry", "knowledge_registry") or _embedded_registry(project_profile, repository_snapshot)
        capability_context = _capability_context(intent_model, project_profile, knowledge_registry, repository_snapshot, options)
        existing_children = _list_option(options, "existingChildren", "existing_children")

        selection = self.selector.select(
            work_item,
            parent_work_item,
            intent_model,
            capability_context,
            project_profile,
            repository_snapshot,
            knowledge_registry,
        )
        duplicate_risks = self.duplicate_detector.detect(
            work_item,
            [item.to_dict() for item in selection["selected_capabilities"]],
            existing_children,
        )
        lineage = build_lineage(work_item, parent_work_item)
        work_type = _type(work_item, intent_model)
        parent_type = _type(parent_work_item, {}) if parent_work_item else None
        role, objective = resolve_generation_role(work_type, parent_type, str(options.get("objective") or ""))
        constraints = _constraints(lineage.derivation_rule)
        risks = [risk.risk for risk in duplicate_risks]
        if selection["rejected_context"]:
            constraints.append("Excluded irrelevant modules, flows, dependencies, applications, and capabilities are recorded in rejectedContext and must not be supplied to generation.")
        if not selection["selected_capabilities"]:
            risks.append("Low capability support: no selected capability survived lineage filtering.")

        confidence = _confidence(intent_model, capability_context, selection, duplicate_risks)
        existing_summaries = [
            ExistingArtifactSummary(
                id=item.get("id"),
                type=str(item.get("type") or "Artifact"),
                title=str(item.get("title") or "Untitled"),
                purpose=str(item.get("purpose") or ""),
                duplicate_risk=bool(item.get("duplicateRisk")),
                reason=str(item.get("reason") or ""),
            )
            for item in summarize_existing_children(existing_children, duplicate_risks)
        ]
        context = PlanningContext(
            work_item_id=_id(work_item, intent_model),
            work_item_type=work_type,
            parent_id=_id(parent_work_item, {}) if parent_work_item else None,
            parent_type=parent_type,
            lineage=lineage,
            business_goal=_business_goal(work_item, parent_work_item, intent_model),
            user_problem=_user_problem(work_item, parent_work_item, intent_model),
            expected_outcome=_expected_outcome(work_item, parent_work_item, intent_model),
            selected_capabilities=selection["selected_capabilities"],
            selected_modules=selection["selected_modules"],
            selected_flows=selection["selected_flows"],
            selected_applications=selection["selected_applications"],
            selected_dependencies=selection["selected_dependencies"],
            selected_standards=selection["selected_standards"],
            rejected_context=selection["rejected_context"],
            generation_role=role,
            generation_objective=objective,
            constraints=constraints,
            risks=risks,
            existing_children=existing_summaries,
            confidence=confidence,
            token_estimate=1,
            diagnostics={},
        )
        payload = context.to_dict()
        token_estimate = estimate_tokens({k: v for k, v in payload.items() if k not in {"tokenEstimate", "diagnostics", "generatedAt"}})
        diagnostics = build_diagnostics(
            intent_keywords=selection["intent_keywords"],
            selected_capabilities=payload["selectedCapabilities"],
            selected_modules=payload["selectedModules"],
            selected_flows=payload["selectedFlows"],
            selected_applications=payload["selectedApplications"],
            selected_dependencies=payload["selectedDependencies"],
            selected_standards=payload["selectedStandards"],
            rejected_context=payload["rejectedContext"],
            duplicate_risks=[risk.to_dict() for risk in duplicate_risks],
            confidence=confidence,
            token_estimate=token_estimate,
        )
        payload["tokenEstimate"] = token_estimate
        payload["diagnostics"] = diagnostics
        return payload


def _intent_model(work_item: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    intent = options.get("intentModel") or options.get("intent_model")
    if isinstance(intent, dict):
        return intent
    return build_intent(work_item)


def _capability_context(intent_model: dict[str, Any], project_profile: dict[str, Any], knowledge_registry: dict[str, Any], repository_snapshot: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    context = options.get("capabilityContext") or options.get("capability_context")
    if isinstance(context, dict):
        return context
    return buildCapabilityContext(
        intent_model,
        {
            "project_profile": project_profile,
            "knowledge_registry": knowledge_registry,
            "repository_snapshot": repository_snapshot,
        },
    )


def _dict_option(options: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = options.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _list_option(options: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = options.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _embedded_registry(project_profile: dict[str, Any], repository_snapshot: dict[str, Any]) -> dict[str, Any]:
    if isinstance(project_profile.get("knowledge_registry"), dict):
        return project_profile["knowledge_registry"]
    if isinstance(repository_snapshot.get("knowledge_registry"), dict):
        return repository_snapshot["knowledge_registry"]
    return {}


def _id(work_item: dict[str, Any] | None, intent_model: dict[str, Any]) -> int | str | None:
    if not work_item:
        return intent_model.get("workItemId") or intent_model.get("work_item_id")
    return work_item.get("id") or work_item.get("workItemId") or work_item.get("work_item_id")


def _type(work_item: dict[str, Any] | None, intent_model: dict[str, Any]) -> str:
    value = ""
    if work_item:
        value = str(work_item.get("type") or work_item.get("workItemType") or work_item.get("work_item_type") or "")
    value = value or str(intent_model.get("workItemType") or intent_model.get("work_item_type") or "Task")
    return value.replace("User Story", "Story")


def _business_goal(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None, intent_model: dict[str, Any]) -> str:
    return _clean(intent_model.get("businessGoal")) or _clean((parent_work_item or {}).get("description")) or _clean(work_item.get("description")) or _clean(work_item.get("title"))


def _user_problem(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None, intent_model: dict[str, Any]) -> str:
    return _clean(intent_model.get("userGoal")) or _clean(work_item.get("description")) or _clean((parent_work_item or {}).get("description")) or "User problem is derived from the selected work item scope."


def _expected_outcome(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None, intent_model: dict[str, Any]) -> str:
    acceptance = _clean(work_item.get("acceptanceCriteria") or work_item.get("acceptance_criteria"))
    if acceptance:
        return acceptance
    return _clean((parent_work_item or {}).get("expectedOutcome") or (parent_work_item or {}).get("expected_outcome")) or _clean(intent_model.get("businessGoal")) or "Generated artifacts remain traceable to the parent work item and selected planning context."


def _constraints(rule: str) -> list[str]:
    return [
        rule,
        "Do not call an LLM from Planning Intelligence.",
        "Do not pass raw project profile or broad module lists to generation.",
        "Every selected reference must be supported by parent intent, capability context, repository evidence, or knowledge registry evidence.",
    ]


def _confidence(intent_model: dict[str, Any], capability_context: dict[str, Any], selection: dict[str, list[Any]], duplicate_risks: list[Any]) -> float:
    score = float(intent_model.get("confidence", 0.45) or 0.45) * 0.35
    score += float(capability_context.get("confidence", 0.45) or 0.45) * 0.35
    score += min(len(selection.get("selected_capabilities", [])), 4) * 0.04
    score += min(len(selection.get("selected_modules", [])), 4) * 0.035
    score += min(len(selection.get("selected_flows", [])), 4) * 0.035
    score -= min(len(duplicate_risks), 3) * 0.04
    return round(max(0.1, min(score, 0.96)), 2)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_clean(item) for item in value if _clean(item))
    return " ".join(str(value).strip().split())
