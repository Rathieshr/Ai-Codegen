from __future__ import annotations

from typing import Any

from .responsibility_extractor import extractBusinessResponsibilities
from .story_analysis import StoryAnalysis
from .story_boundary_builder import buildStoryPlanningBoundary
from .story_dependency_builder import buildStoryDependencies
from .story_evidence_collector import collectStoryRepositoryEvidence
from .story_analysis_validator import validateStoryAnalysis
from .story_generation import generateStoryFromJourney
from .user_journey_discovery import discoverUserJourneys


class StoryAnalysisEngine:
    """Derive user journeys and story candidates from approved Feature DNA."""

    def analyze(
        self,
        feature: dict[str, Any],
        feature_dna: dict[str, Any],
        *,
        profile: dict[str, Any] | None = None,
        capability_review: dict[str, Any] | None = None,
        planning_boundary: dict[str, Any] | None = None,
        validation_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = profile or {}
        responsibilities = extractBusinessResponsibilities(feature_dna, feature)
        boundary = buildStoryPlanningBoundary({**feature_dna, "planningBoundary": planning_boundary or feature_dna.get("planningBoundary")}, responsibilities)
        evidence = collectStoryRepositoryEvidence(feature_dna, profile)
        dependencies = buildStoryDependencies(feature_dna, [item.name for item in evidence])
        themes = _acceptance_themes(feature_dna, responsibilities)
        journeys = discoverUserJourneys(
            responsibilities,
            personas=_personas(feature_dna, profile),
            evidence=evidence,
            dependencies=dependencies,
            boundary=boundary,
            acceptance_themes=themes,
        )
        system_responsibilities = _system_responsibilities(evidence)
        analysis = StoryAnalysis(
            feature_id=feature.get("id") or feature_dna.get("workItemId"),
            feature_dna=str(feature_dna.get("dnaId") or ""),
            business_responsibilities=responsibilities,
            user_journeys=journeys,
            system_responsibilities=system_responsibilities,
            acceptance_themes=themes,
            planning_boundary=boundary,
            repository_evidence=evidence,
            dependencies=dependencies,
            implementation_areas=_implementation_areas(evidence),
            confidence=_confidence(evidence, journeys, validation_summary or feature_dna.get("validationSummary")),
            diagnostics={},
        )
        validation = validateStoryAnalysis(analysis)
        payload = analysis.to_dict()
        payload["validation"] = validation
        payload["diagnostics"] = {
            "journeyCount": len(payload["userJourneys"]),
            "storyCount": 0,
            "repositoryCoverage": min(100, len(evidence) * 20),
            "knowledgeCoverage": min(100, len(responsibilities) * 12),
            "dependencyCount": len(dependencies),
            "validationScore": validation["score"],
            "confidence": payload["confidence"],
            "storyReadiness": validation["planningReadiness"],
        }
        return payload

    def generate_story_for_journey(
        self,
        journey: dict[str, Any],
        feature_dna: dict[str, Any],
        *,
        existing_responsibilities: list[str] | None = None,
    ) -> dict[str, Any]:
        from .story_analysis import Dependency, PlanningBoundary, RepositoryEvidence, UserJourney

        boundary_payload = journey.get("planningBoundary") if isinstance(journey.get("planningBoundary"), dict) else {}
        user_journey = UserJourney(
            journey_id=str(journey.get("journeyId") or ""),
            journey_name=str(journey.get("journeyName") or ""),
            business_responsibility=str(journey.get("businessResponsibility") or ""),
            business_value=str(journey.get("businessValue") or ""),
            persona=str(journey.get("persona") or "Operations User"),
            dependencies=[
                Dependency(name=str(item.get("name") or ""), reason=str(item.get("reason") or ""), confidence=float(item.get("confidence") or 0.7))
                for item in journey.get("dependencies", [])
                if isinstance(item, dict)
            ],
            repository_evidence=[
                RepositoryEvidence(
                    name=str(item.get("name") or ""),
                    type=str(item.get("type") or "Module"),
                    confidence=float(item.get("confidence") or 0.7),
                    reason=str(item.get("reason") or ""),
                    source=str(item.get("source") or "story_analysis"),
                )
                for item in journey.get("repositoryEvidence", [])
                if isinstance(item, dict)
            ],
            planning_boundary=PlanningBoundary(
                in_scope=[str(item) for item in boundary_payload.get("inScope", [])],
                out_of_scope=[str(item) for item in boundary_payload.get("outOfScope", [])],
            ),
            acceptance_themes=[str(item) for item in journey.get("acceptanceThemes", [])],
            confidence=float(journey.get("confidence") or 0.7),
            status=str(journey.get("status") or "draft"),
            order=int(journey.get("order") or 0),
        )
        return generateStoryFromJourney(user_journey, feature_dna=feature_dna, existing_responsibilities=existing_responsibilities)


def analyzeFeatureStories(feature: dict[str, Any], feature_dna: dict[str, Any], profile: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    return StoryAnalysisEngine().analyze(feature, feature_dna, profile=profile, **kwargs)


def _acceptance_themes(feature_dna: dict[str, Any], responsibilities: list[str]) -> list[str]:
    themes = _string_list(feature_dna.get("acceptanceThemes"))
    text = " ".join([*responsibilities, feature_dna.get("capability") or ""]).lower()
    if "search" in text:
        themes.append("Search")
    if "filter" in text:
        themes.append("Filtering")
    if "detail" in text or "review" in text:
        themes.extend(["Accuracy", "Data Quality"])
    if "audit" in text or "acknowledge" in text:
        themes.append("Audit")
    return _unique([*themes, "Visibility", "Security", "Error Handling"])


def _personas(feature_dna: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    personas = _string_list(feature_dna.get("personas")) or _string_list(profile.get("users")) or _string_list(profile.get("actors"))
    return personas or ["Operations User"]


def _system_responsibilities(evidence: list[Any]) -> list[str]:
    names = [item.name for item in evidence]
    result: list[str] = []
    for name in names:
        lowered = name.lower()
        if "telemetry" in lowered:
            result.append("Collect telemetry")
        elif "fault" in lowered:
            result.append("Persist fault event")
            result.append("Evaluate severity")
        elif "audit" in lowered:
            result.append("Audit user activity")
    return _unique(result) or ["Retrieve approved feature data", "Apply role-based access rules"]


def _implementation_areas(evidence: list[Any]) -> list[str]:
    return _unique([item.name for item in evidence if item.type in {"Module", "Service", "File"}])[:8]


def _confidence(evidence: list[Any], journeys: list[Any], validation_summary: Any) -> float:
    score = 0.55
    if evidence:
        score += 0.18
    if len(journeys) >= 4:
        score += 0.12
    if isinstance(validation_summary, dict):
        score += min(0.1, float(validation_summary.get("score") or 0) / 1000)
    return min(0.95, round(score, 2))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [" ".join(str(item).split()) for item in value if " ".join(str(item).split())]
    text = " ".join(str(value).split())
    return [text] if text else []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result

