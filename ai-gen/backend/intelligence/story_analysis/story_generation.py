from __future__ import annotations

from typing import Any

from .story_analysis import UserJourney
from .story_analysis_validator import validateGeneratedStory


def generateStoryFromJourney(
    journey: UserJourney,
    *,
    feature_dna: dict[str, Any],
    existing_responsibilities: list[str] | None = None,
) -> dict[str, Any]:
    title = _story_title(journey)
    coverage_area = _coverage_area(journey)
    description = f"As a {journey.persona}, I want to {journey.journey_name[0].lower() + journey.journey_name[1:]} so that {journey.business_value[0].lower() + journey.business_value[1:]}"
    acceptance_criteria = _acceptance_criteria(journey, coverage_area)
    validation = validateGeneratedStory(journey, existing_responsibilities)
    evidence_names = [item.name for item in journey.repository_evidence]
    dependency_names = [item.name for item in journey.dependencies]
    return {
        "title": title,
        "user_persona": journey.persona,
        "persona": journey.persona,
        "goal": journey.journey_name,
        "user_goal": journey.business_responsibility,
        "business_value": journey.business_value,
        "description": description,
        "acceptance_criteria": acceptance_criteria,
        "repository_evidence": [item.to_dict() for item in journey.repository_evidence],
        "dependencies": dependency_names,
        "implementation_constraints": list(journey.planning_boundary.in_scope),
        "acceptance_themes": list(journey.acceptance_themes),
        "confidence": journey.confidence,
        "journey_id": journey.journey_id,
        "business_responsibility": journey.business_responsibility,
        "coverage_area": coverage_area,
        "user_action": journey.journey_name,
        "planning_boundary": journey.planning_boundary.to_dict(),
        "modules_used": [item.name for item in journey.repository_evidence if item.type == "Module"],
        "flows_used": [item.name for item in journey.repository_evidence if item.type == "Flow"],
        "supporting_context": {"repositoryEvidence": evidence_names, "dependencies": dependency_names},
        "validationReport": validation,
        "status": "preview" if validation["valid"] else "blocked_by_story_validation",
        "parent_feature_dna": feature_dna.get("dnaId"),
        "acceptance_criteria_count": len(acceptance_criteria),
        "story_quality_score": int((validation.get("summary") or {}).get("score") or 80),
        "acceptance_criteria_quality_score": 85,
    }


def _story_title(journey: UserJourney) -> str:
    title = journey.journey_name.strip()
    return title if title else journey.business_responsibility.strip() or "Review User Journey"


def _acceptance_criteria(journey: UserJourney, coverage_area: str) -> list[str]:
    subject = journey.business_responsibility.lower()
    criteria = _domain_acceptance_criteria(journey, coverage_area)
    if not criteria:
        criteria = [
            f"{journey.persona} can complete {subject} from the approved feature entry point.",
            f"The outcome supports {journey.journey_name.lower()} without crossing out-of-scope behavior.",
            "Unavailable or missing data is clearly explained without hiding available information.",
            "Access follows the approved role and permission rules.",
        ]
    if any(theme.lower() in {"audit", "security"} for theme in journey.acceptance_themes):
        criteria.append("The action is traceable with user identity, timestamp, and affected record identifier.")
    if any(theme.lower() in {"performance", "search", "filtering"} for theme in journey.acceptance_themes):
        criteria.append("The result is returned within the approved performance expectation for normal project data volume.")
    return _unique(criteria)


def _domain_acceptance_criteria(journey: UserJourney, coverage_area: str) -> list[str]:
    text = f"{journey.journey_name} {journey.business_responsibility}".lower()
    if not any(token in text for token in ["fault", "event", "severity", "outage"]):
        return []
    if coverage_area == "View":
        return [
            "The list shows Device ID, Fault Type, Severity, Timestamp, and Status for each event.",
            "Events are sorted by Severity and Timestamp so the highest-risk items appear first.",
            "Users without permission cannot view restricted fault event information.",
            "The list refreshes without duplicating existing events.",
        ]
    if coverage_area == "Details":
        return [
            "The detail view shows Location, Telemetry Context, Event History, and Outage Context.",
            "Missing device or telemetry values are labelled as Data Unavailable.",
            "The user can return to the previous event list without losing position.",
            "Restricted detail fields are hidden when the user does not have permission.",
        ]
    if coverage_area == "Search":
        return [
            "The user can search by Device ID or Event ID.",
            "Partial matches return matching fault events without requiring an exact identifier.",
            "Search results are returned within 3 seconds for normal project data volume.",
            "A no-results message is shown when no fault events match the search.",
        ]
    if coverage_area == "Filter":
        return [
            "The user can filter by Severity, Status, and Time Range.",
            "The user can reset all filters and return to the full event list.",
            "Filter changes update the visible events without clearing the current search text.",
            "A no-results message is shown when filters exclude every event.",
        ]
    if coverage_area == "Notifications":
        return [
            "New critical fault events are clearly surfaced to permitted operations users.",
            "The notification includes the event identifier, severity, device reference, and timestamp.",
            "The user can open the relevant event directly from the notification.",
            "Duplicate notifications are suppressed for the same event update.",
        ]
    if coverage_area == "Empty states":
        return [
            "When no fault events are available, the user sees a clear empty-state explanation.",
            "Missing telemetry or device data is shown without blocking available event details.",
            "The empty state provides a safe refresh or retry action.",
            "Errors do not remove the last successfully loaded event information.",
        ]
    if coverage_area == "Audit requirements":
        return [
            "Viewing or changing a fault event records user identity, timestamp, and event identifier.",
            "Audit entries distinguish view, search, filter, and detail actions.",
            "Audit history is available for authorized review.",
            "Audit capture failures are visible to support teams without exposing restricted data.",
        ]
    return []


def _coverage_area(journey: UserJourney) -> str:
    text = f"{journey.journey_name} {journey.business_responsibility}".lower()
    if "search" in text:
        return "Search"
    if "filter" in text:
        return "Filter"
    if any(token in text for token in ["audit", "record", "acknowledge"]):
        return "Audit requirements"
    if any(token in text for token in ["detail", "review"]):
        return "Details"
    if any(token in text for token in ["unavailable", "missing", "error", "empty"]):
        return "Empty states"
    if any(token in text for token in ["notify", "alert", "newly arrived", "live awareness"]):
        return "Notifications"
    return "View"


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
