from __future__ import annotations

from .story_analysis import StoryAnalysis, UserJourney


def validateStoryAnalysis(analysis: StoryAnalysis) -> dict[str, object]:
    issues: list[str] = []
    if not analysis.feature_dna:
        issues.append("Feature DNA is required.")
    if not analysis.business_responsibilities:
        issues.append("At least one business responsibility is required.")
    if not analysis.user_journeys:
        issues.append("At least one user journey is required.")
    names = [journey.journey_name.lower() for journey in analysis.user_journeys]
    if len(names) != len(set(names)):
        issues.append("User journeys must be unique.")
    if not analysis.acceptance_themes:
        issues.append("Acceptance themes are required before story generation.")
    if not analysis.planning_boundary.in_scope:
        issues.append("Planning boundary must define in-scope behavior.")
    score = max(0, 100 - len(issues) * 20)
    return {
        "status": "PASS" if not issues and score >= 80 else "NEEDS_REVIEW",
        "score": score,
        "issues": issues,
        "planningReadiness": "PASS" if not issues and score >= 80 else "NEEDS_REVIEW",
    }


def validateGeneratedStory(journey: UserJourney, existing_responsibilities: list[str] | None = None) -> dict[str, object]:
    issues: list[str] = []
    existing = {item.lower() for item in existing_responsibilities or []}
    if journey.business_responsibility.lower() in existing:
        issues.append(f"Duplicate responsibility: {journey.business_responsibility}.")
    if not journey.acceptance_themes:
        issues.append("Story is missing acceptance themes.")
    if not journey.planning_boundary.in_scope:
        issues.append("Story has no planning boundary.")
    score = max(0, 100 - len(issues) * 35)
    status = "Approved" if not issues and score >= 80 else "Rejected"
    return {"valid": status == "Approved", "status": status, "issues": issues, "summary": {"score": score, "issues": issues}}

