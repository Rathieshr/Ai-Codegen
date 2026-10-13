from __future__ import annotations

import time
from typing import Any

from .business_goal_extractor import desired_outcomes, extract_business_goals
from .business_problem_extractor import extract_business_problems
from .capability_extractor import extract_excluded_capabilities, extract_required_capabilities
from .capability_prioritizer import prioritize_capabilities
from .capability_relationship_builder import build_capability_relationships
from .epic_analysis import EpicAnalysis
from .epic_analysis_validator import validate_epic_analysis
from .planning_boundary_builder import build_planning_boundary
from .repository_evidence_collector import collect_all_repository_evidence


class EpicAnalysisEngine:
    def analyze_epic(
        self,
        epic: dict[str, Any],
        profile: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        profile = profile or {}
        options = options or {}
        keywords = _string_list(options.get("intent_keywords") or options.get("keywords"))
        business_problems = extract_business_problems(epic, profile, keywords)
        business_goals = extract_business_goals(business_problems)
        outcomes = desired_outcomes(business_goals)
        required = extract_required_capabilities(epic, profile, business_problems, business_goals, keywords)
        excluded = extract_excluded_capabilities(epic, profile, required)
        relationships = build_capability_relationships(required)
        priorities = prioritize_capabilities(required)
        boundary = build_planning_boundary(required, excluded)
        validation = validate_epic_analysis(required, excluded, relationships, boundary)
        repository_evidence = collect_all_repository_evidence(profile)
        confidence = _confidence(required, repository_evidence, validation)
        diagnostics = {
            "business_problem_count": len(business_problems),
            "business_goal_count": len(business_goals),
            "capability_count": len(required),
            "excluded_capabilities": [item.name for item in excluded],
            "repository_evidence_count": len(repository_evidence),
            "token_estimate": _token_estimate(epic, business_problems, business_goals, required, excluded),
            "analysis_duration_ms": int((time.perf_counter() - started) * 1000),
            "validation": validation,
        }
        return EpicAnalysis(
            epic_id=epic.get("id") or epic.get("work_item_id") or epic.get("workItemId"),
            business_problems=business_problems,
            business_goals=business_goals,
            desired_outcomes=outcomes,
            required_capabilities=required,
            excluded_capabilities=excluded,
            capability_relationships=relationships,
            capability_priority=priorities,
            planning_boundary=boundary,
            repository_evidence=repository_evidence,
            confidence=confidence,
            diagnostics=diagnostics,
        ).to_dict()


def analyze_epic(epic: dict[str, Any], profile: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return EpicAnalysisEngine().analyze_epic(epic, profile, options)


def analyzeEpic(epic: dict[str, Any], profile: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return analyze_epic(epic, profile, options)


def _confidence(required: list[Any], repository_evidence: list[dict[str, Any]], validation: dict[str, Any]) -> float:
    score = 0.48 + min(len(required), 5) * 0.06 + min(len(repository_evidence), 10) * 0.015
    if validation.get("status") == "Approved":
        score += 0.08
    return round(min(score, 0.96), 2)


def _token_estimate(epic: dict[str, Any], problems: list[str], goals: list[str], required: list[Any], excluded: list[Any]) -> int:
    text = " ".join(
        [
            str(epic.get("title") or ""),
            str(epic.get("description") or ""),
            " ".join(problems),
            " ".join(goals),
            " ".join(item.name for item in required),
            " ".join(item.name for item in excluded),
        ]
    )
    return max(1, len(text.split()))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [" ".join(str(item).split()) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [" ".join(part.split()) for part in value.replace("\n", "|").split("|") if part.strip()]
    return []
