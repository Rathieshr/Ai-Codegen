from __future__ import annotations


ROLE_BY_OUTPUT_TYPE = {
    "Epic": "Product Owner",
    "EpicRefinement": "Product Owner",
    "Feature": "Product Manager / Solution Architect",
    "FeatureRecommendation": "Product Manager / Solution Architect",
    "Story": "Scrum Master / Business Analyst",
    "StoryRecommendation": "Scrum Master / Business Analyst",
    "Task": "Senior Developer",
    "TaskRecommendation": "Senior Developer",
}

OBJECTIVE_BY_OUTPUT_TYPE = {
    "Epic": "Improve business outcome, business value, scope, and success metrics without introducing implementation.",
    "EpicRefinement": "Improve business outcome, business value, scope, and success metrics without introducing implementation.",
    "Feature": "Generate product capabilities. Each feature solves one capability, avoids overlap, and has measurable value.",
    "FeatureRecommendation": "Generate product capabilities. Each feature solves one capability, avoids overlap, and has measurable value.",
    "Story": "Generate independent, valuable, testable, sprint-ready stories derived from the selected feature intent.",
    "StoryRecommendation": "Generate independent, valuable, testable, sprint-ready stories derived from the selected feature intent.",
    "Task": "Generate implementation tasks that map to story acceptance criteria and selected repository context.",
    "TaskRecommendation": "Generate implementation tasks that map to story acceptance criteria and selected repository context.",
}


def resolve_role(output_type: str) -> str:
    return ROLE_BY_OUTPUT_TYPE.get(_normalized(output_type), "Product Owner")


def resolve_objective(output_type: str) -> str:
    return OBJECTIVE_BY_OUTPUT_TYPE.get(_normalized(output_type), "Generate a planning artifact from the supplied PlanningContext.")


def _normalized(output_type: str) -> str:
    return "".join(part.capitalize() for part in str(output_type or "").replace("_", " ").replace("-", " ").split())

