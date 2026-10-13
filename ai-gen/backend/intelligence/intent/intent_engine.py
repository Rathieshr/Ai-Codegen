from __future__ import annotations

from typing import Any

from .intent_classifier import (
    detect_actions,
    detect_capabilities,
    detect_domain,
    detect_entities,
    detect_personas,
    detect_technical_keywords,
    infer_flows,
    infer_modules,
)
from .intent_confidence import score_intent
from .intent_diagnostics import IntentDiagnostics
from .intent_extractor import clean_text, extract_keywords, extract_user_story_goal, normalize_type, work_item_text
from .intent_model import IntentModel


class IntentEngine:
    def build_intent(self, work_item: dict[str, Any]) -> dict[str, Any]:
        diagnostics = IntentDiagnostics()
        title = clean_text(work_item.get("title"))
        description = clean_text(work_item.get("description"))
        acceptance = clean_text(work_item.get("acceptance_criteria") or work_item.get("acceptanceCriteria"))
        business_value = clean_text(work_item.get("business_value") or work_item.get("businessValue"))
        text = work_item_text(work_item)
        work_item_type = normalize_type(work_item.get("type") or work_item.get("work_item_type") or work_item.get("workItemType"))

        explicit_goal, explicit_personas = extract_user_story_goal(text, diagnostics)
        personas = _unique([*explicit_personas, *detect_personas(text, diagnostics)])
        primary_capability, secondary_capabilities = detect_capabilities(text, diagnostics)
        business_domain = detect_domain(text, diagnostics)
        actions = detect_actions(text, diagnostics)
        entities = detect_entities(text, diagnostics)
        technical_keywords = detect_technical_keywords(text, diagnostics)
        inferred_modules = infer_modules(text, diagnostics)
        inferred_flows = infer_flows(text, diagnostics)
        business_keywords = _business_keywords(text, technical_keywords)

        business_goal = _business_goal(work_item_type, title, description, business_value, primary_capability, business_domain)
        user_goal = explicit_goal or _inferred_user_goal(personas, actions, entities, primary_capability)
        if business_goal:
            diagnostics.add("Business goal derived from work item title, description, or business value.")
        if user_goal and not explicit_goal:
            diagnostics.add("User goal inferred from persona, action, entity, and capability signals.")

        confidence = score_intent(
            has_title=bool(title),
            has_description=bool(description),
            has_acceptance=bool(acceptance),
            persona_count=len(personas),
            action_count=len(actions),
            entity_count=len(entities),
            module_count=len(inferred_modules),
            flow_count=len(inferred_flows),
            reasoning_count=len(diagnostics.reasoning),
        )

        model = IntentModel(
            work_item_id=work_item.get("id") or work_item.get("workItemId") or work_item.get("work_item_id"),
            work_item_type=work_item_type,  # type: ignore[arg-type]
            business_goal=business_goal,
            user_goal=user_goal,
            primary_capability=primary_capability,
            secondary_capabilities=secondary_capabilities,
            personas=personas,
            business_domain=business_domain,
            business_keywords=business_keywords,
            technical_keywords=technical_keywords,
            actions=actions,
            entities=entities,
            inferred_modules=inferred_modules,
            inferred_flows=inferred_flows,
            confidence=confidence,
            reasoning=diagnostics.reasoning,
        )
        return model.to_dict()


def build_intent(work_item: dict[str, Any]) -> dict[str, Any]:
    return IntentEngine().build_intent(work_item)


def buildIntent(work_item: dict[str, Any]) -> dict[str, Any]:
    return build_intent(work_item)


def _business_goal(work_item_type: str, title: str, description: str, business_value: str, capability: str, domain: str) -> str:
    if business_value:
        return business_value
    if work_item_type == "Epic" and title:
        return f"Deliver {title} as a strategic {domain.lower()} capability."
    if work_item_type == "Feature" and title:
        return f"Enable {title} as a focused {capability.lower()} capability."
    if title and description:
        return f"Deliver {title}: {description[:180]}"
    if title:
        return f"Deliver {title}."
    return f"Clarify and deliver the {capability.lower()} outcome."


def _inferred_user_goal(personas: list[str], actions: list[str], entities: list[str], capability: str) -> str:
    persona = personas[0] if personas else "User"
    action = actions[0].lower() if actions else "use"
    entity = entities[0].lower() if entities else capability.lower()
    return f"{persona} wants to {action} {entity} effectively."


def _business_keywords(text: str, technical_keywords: list[str]) -> list[str]:
    technical = {keyword.lower() for keyword in technical_keywords}
    return [keyword for keyword in extract_keywords(text) if keyword.lower() not in technical][:18]


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output

