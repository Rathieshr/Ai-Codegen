from __future__ import annotations

import hashlib

from .story_analysis import Dependency, PlanningBoundary, RepositoryEvidence, UserJourney


def discoverUserJourneys(
    responsibilities: list[str],
    *,
    personas: list[str],
    evidence: list[RepositoryEvidence],
    dependencies: list[Dependency],
    boundary: PlanningBoundary,
    acceptance_themes: list[str],
) -> list[UserJourney]:
    user = personas[0] if personas else "Operations User"
    journeys: list[UserJourney] = []
    for index, responsibility in enumerate(_unique(responsibilities)):
        action = _journey_action(responsibility)
        journey_name = _journey_name(action, responsibility)
        journeys.append(
            UserJourney(
                journey_id=_journey_id(journey_name),
                journey_name=journey_name,
                business_responsibility=responsibility,
                business_value=_business_value(action, responsibility),
                persona=user,
                dependencies=dependencies[:3],
                repository_evidence=evidence[:5],
                planning_boundary=boundary,
                acceptance_themes=_themes_for_action(action, acceptance_themes),
                confidence=0.86 if evidence else 0.68,
                status="draft",
                order=index + 1,
            )
        )
    return journeys


def _journey_action(responsibility: str) -> str:
    lowered = responsibility.lower()
    if any(token in lowered for token in ["detail", "review", "open"]):
        return "Review"
    if "search" in lowered or "find" in lowered:
        return "Search"
    if "filter" in lowered:
        return "Filter"
    if any(token in lowered for token in ["audit", "acknowledge", "note"]):
        return "Record"
    if any(token in lowered for token in ["detect", "view", "display", "list"]):
        return "View"
    if any(token in lowered for token in ["unavailable", "missing", "error", "exception"]):
        return "Handle"
    return "Use"


def _journey_name(action: str, responsibility: str) -> str:
    cleaned = " ".join(str(responsibility).split())
    if cleaned.lower().startswith(action.lower()):
        return cleaned
    return f"{action} {cleaned[0].lower() + cleaned[1:]}" if cleaned else action


def _business_value(action: str, responsibility: str) -> str:
    if action == "View":
        return "The user can see the operational information needed to begin work."
    if action == "Review":
        return "The user can make an informed operational decision with enough context."
    if action == "Search":
        return "The user can quickly locate the specific record or evidence they need."
    if action == "Filter":
        return "The user can narrow the result set to the highest-value information."
    if action == "Record":
        return "The team has traceability for operational review and follow-up."
    if action == "Handle":
        return "The user can recover safely when expected data is missing or unavailable."
    return f"The user can complete {responsibility.lower()} as an independent outcome."


def _themes_for_action(action: str, themes: list[str]) -> list[str]:
    defaults = {
        "View": ["Visibility", "Sorting", "Security", "Accessibility"],
        "Review": ["Accuracy", "Data Quality", "Security", "Audit"],
        "Search": ["Search", "Performance", "Security", "Empty State"],
        "Filter": ["Filtering", "Sorting", "Performance", "Empty State"],
        "Record": ["Audit", "Security", "Data Quality"],
        "Handle": ["Error Handling", "Empty State", "Data Quality"],
    }
    selected = defaults.get(action, ["Visibility", "Accuracy", "Security"])
    return _unique([*selected, *themes])[:6]


def _journey_id(value: str) -> str:
    return f"journey_{hashlib.sha1(value.lower().encode('utf-8')).hexdigest()[:10]}"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split())
        key = cleaned.lower()
        if key and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result

