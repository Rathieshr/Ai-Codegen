from __future__ import annotations


def extract_business_goals(business_problems: list[str]) -> list[str]:
    goals: list[str] = []
    for problem in business_problems:
        lowered = problem.lower()
        if "visibility" in lowered:
            goals.append("Provide unified operational visibility with reviewable live status across selected systems.")
        elif "fault" in lowered:
            goals.append("Improve critical fault detection and review speed with measurable event visibility.")
        elif "alert" in lowered:
            goals.append("Improve operator response time by making urgent alerts actionable and traceable.")
        elif "outage" in lowered or "investigation" in lowered:
            goals.append("Improve fault investigation by correlating outage, telemetry, and device health evidence.")
        elif "reliability" in lowered or "trend" in lowered:
            goals.append("Support operational analytics with measurable reliability trend visibility.")
        else:
            goals.append("Define independently deliverable capability outcomes before feature generation.")
    return _unique(goals)


def desired_outcomes(goals: list[str]) -> list[str]:
    outcomes: list[str] = []
    for goal in goals:
        lowered = goal.lower()
        if "visibility" in lowered:
            outcomes.append("Operations users can review current operational state without switching between disconnected views.")
        elif "fault" in lowered:
            outcomes.append("Critical fault events are visible with severity, device, timing, and current status.")
        elif "response" in lowered or "alert" in lowered:
            outcomes.append("Operators can identify and act on urgent alerts with clear ownership and audit trail.")
        elif "investigation" in lowered:
            outcomes.append("Outage investigation starts from trusted event context and preserves a reviewable timeline.")
        elif "analytics" in lowered or "trend" in lowered:
            outcomes.append("Managers can compare reliability trends and prioritize operational improvements.")
    return _unique(outcomes) or ["Planning output has measurable business outcomes before feature generation."]


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
