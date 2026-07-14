"""Explainable estimation and dependency intelligence over synchronized ADO data."""

from __future__ import annotations

import html
import re
from datetime import datetime
from statistics import median
from typing import Any

from backend.platform_sdk import as_azure_devops_sdk
from uuid import uuid4

from .estimation_models import EstimationRecommendation, EstimationStatus
from .estimation_repository import EstimationRepository
from .models import RecommendationStatus, WorkItemRecommendation, now_iso
from .repository import WorkItemRecommendationRepository
from .service import RecommendationNotFoundError, StaleRecommendationError, WorkItemNotFoundError


POINTS = (1, 2, 3, 5, 8, 13)
EFFORT = {
    1: ("0.5-1 day", "0.5-1 day", "0.5 day"),
    2: ("1-2 days", "0.5-1 day", "0.5 day"),
    3: ("2-3 days", "1-2 days", "0.5-1 day"),
    5: ("2-4 days", "1-2 days", "0.5-1 day"),
    8: ("4-7 days", "2-3 days", "1-2 days"),
    13: ("7-12 days", "3-5 days", "1-2 days"),
}
COMPLETED_STATES = {"closed", "completed", "done", "resolved"}


class EstimationIntelligenceService:
    """Build estimates without provider calls or direct Azure DevOps writes."""

    def __init__(
        self,
        *,
        azure_devops: Any,
        estimates: EstimationRepository,
        recommendations: WorkItemRecommendationRepository,
        engineering_memory: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.ado_sdk = as_azure_devops_sdk(azure_devops)
        self.estimates = estimates
        self.recommendations = recommendations
        self.engineering_memory = engineering_memory
        self.platform = platform

    def handle(self, work_item_id: str, request: dict[str, Any] | None = None, *, correlation_id: str = "") -> dict[str, Any]:
        request = request or {}
        action = str(request.get("action") or "generate").strip().lower()
        if action in {"generate", "regenerate"}:
            return self.estimate(work_item_id, request, correlation_id=correlation_id)
        estimate_id = str(request.get("estimateId") or "")
        if not estimate_id:
            raise ValueError("estimateId is required for estimate decisions.")
        if action == "accept":
            return self.accept(estimate_id, str(request.get("actor") or ""))
        if action == "edit":
            return self.edit(estimate_id, request)
        if action == "reject":
            return self.reject(estimate_id, str(request.get("actor") or ""))
        if action in {"recordoutcome", "record_outcome"}:
            return self.record_outcome(estimate_id, request)
        raise ValueError(f"Unsupported estimation action: {action}.")

    def estimate(self, work_item_id: str, request: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        item, project_id = self._resolve(work_item_id, str(request.get("projectId") or ""))
        team_id = str(request.get("teamId") or item.get("teamId") or "")
        criteria = _criteria(item.get("acceptanceCriteria"))
        analysis = self.recommendations.latest_analysis(work_item_id) or {}
        decomposition = _strings(request.get("decomposition") or analysis.get("decompositionRecommendations"))
        repository_impact = _repository_impact(request, analysis)
        dependencies = _dependencies(request, analysis, item)
        historical = self._historical(project_id, work_item_id)
        similar = _similar_items(item, historical, repository_impact)
        calibration = self.accuracy(project_id, team_id, include_items=False)
        memories = self._memory(project_id, item, repository_impact)
        points = _story_points(item, criteria, decomposition, repository_impact, dependencies, similar, calibration)
        development, testing, review = EFFORT[points]
        uncertainty = _uncertainty(criteria, repository_impact, historical, similar, dependencies, request)
        confidence = _confidence(criteria, repository_impact, similar, calibration, uncertainty)
        suggested_tasks = _tasks(item, criteria, decomposition, repository_impact, memories)
        blockers = _blockers(criteria, repository_impact, dependencies, request)
        assumptions = [
            "Effort ranges assume a normal working-day calendar and the current approved scope.",
            "Story points are relative complexity, not elapsed time or an individual productivity measure.",
            "Repository facts override historical estimates and Engineering Memory.",
        ]
        if not historical:
            assumptions.append("No completed project history was available; the estimate uses scope complexity only.")
        estimate = EstimationRecommendation.create(
            work_item_id=str(work_item_id), work_item_revision=int(item.get("revision") or 0),
            project_id=project_id, team_id=team_id, suggested_tasks=suggested_tasks,
            story_points=points, effort_range={"development": development, "qa": testing, "review": review},
            testing_effort=testing, review_effort=review, uncertainty=uncertainty, confidence=confidence,
            dependencies=dependencies, blockers=blockers, assumptions=assumptions,
            similar_historical_items=similar, calibration=calibration,
            repository_impact=repository_impact,
            evidence=_evidence(criteria, repository_impact, similar, memories, analysis),
        )
        result = self.estimates.save(estimate)
        result["memoryContext"] = memories
        result["correlationId"] = correlation_id or f"corr-{uuid4().hex[:16]}"
        self._event("AzureDevOpsEstimateGenerated", result)
        return result

    def get(self, work_item_id: str, project_id: str = "") -> dict[str, Any]:
        estimate = self.estimates.latest(work_item_id)
        if not estimate or (project_id and estimate.project_id != project_id):
            raise RecommendationNotFoundError(f"No estimate exists for work item {work_item_id}")
        self._mark_stale(estimate)
        return estimate.to_dict()

    def accept(self, estimate_id: str, actor: str) -> dict[str, Any]:
        estimate = self._active(estimate_id)
        estimate.status = EstimationStatus.ACCEPTED
        estimate.accepted_by = actor or "current-user"
        recommendation = WorkItemRecommendation(
            recommendation_id=f"wir-estimate-{uuid4().hex[:14]}", work_item_id=estimate.work_item_id,
            work_item_revision=estimate.work_item_revision, recommendation_type="StoryPointRecommendation",
            current_value=None, proposed_value={"points": estimate.story_points, "effortRange": estimate.effort_range},
            reasons=["Accepted explainable estimate; Azure DevOps application remains approval-controlled."],
            evidence=estimate.evidence[:12], confidence=estimate.confidence,
            status=RecommendationStatus.APPROVED, approved_by=estimate.accepted_by, approved_at=now_iso(),
            analysis_id=estimate.estimate_id, project_id=estimate.project_id,
        )
        self.recommendations.save(recommendation)
        estimate.automation_recommendation_id = recommendation.recommendation_id
        result = self.estimates.save(estimate)
        self._event("AzureDevOpsEstimateAccepted", result)
        return result

    def edit(self, estimate_id: str, request: dict[str, Any]) -> dict[str, Any]:
        source = self._active(estimate_id)
        points = int(request.get("storyPoints") or 0)
        if points not in POINTS:
            raise ValueError("storyPoints must be one of 1, 2, 3, 5, 8, or 13.")
        development, testing, review = EFFORT[points]
        edited = EstimationRecommendation.create(
            work_item_id=source.work_item_id, work_item_revision=source.work_item_revision,
            project_id=source.project_id, team_id=source.team_id, suggested_tasks=source.suggested_tasks,
            story_points=points, effort_range={"development": development, "qa": testing, "review": review},
            testing_effort=testing, review_effort=review, uncertainty=source.uncertainty,
            confidence=source.confidence, dependencies=source.dependencies, blockers=source.blockers,
            assumptions=source.assumptions, similar_historical_items=source.similar_historical_items,
            calibration=source.calibration, repository_impact=source.repository_impact,
            evidence=source.evidence, status=EstimationStatus.EDITED,
            edit_reason=str(request.get("editReason") or "Human-adjusted estimate."),
            parent_estimate_id=source.estimate_id,
        )
        return self.estimates.save(edited)

    def reject(self, estimate_id: str, actor: str) -> dict[str, Any]:
        estimate = self._active(estimate_id)
        estimate.status = EstimationStatus.REJECTED
        estimate.rejected_by = actor or "current-user"
        result = self.estimates.save(estimate)
        self._event("AzureDevOpsEstimateRejected", result)
        return result

    def record_outcome(self, estimate_id: str, request: dict[str, Any]) -> dict[str, Any]:
        estimate = self.estimates.get(estimate_id)
        if not estimate:
            raise RecommendationNotFoundError(estimate_id)
        cycle = _optional_positive(request.get("actualCycleTimeDays"), "actualCycleTimeDays")
        active = _optional_positive(request.get("actualActiveTimeDays"), "actualActiveTimeDays")
        if cycle is None:
            raise ValueError("actualCycleTimeDays is required to record an outcome.")
        outcome = self.estimates.save_outcome(estimate_id, {
            "projectId": estimate.project_id, "teamId": estimate.team_id,
            "actualCycleTimeDays": cycle, "actualActiveTimeDays": active,
            "reopenCount": int(request.get("reopenCount") or 0),
            "prIterations": int(request.get("prIterations") or 0),
            "escapedDefects": int(request.get("escapedDefects") or 0),
        })
        self._event("AzureDevOpsEstimateOutcomeRecorded", outcome)
        return {"outcome": outcome, "calibration": self.accuracy(estimate.project_id, estimate.team_id)}

    def accuracy(self, project_id: str, team_id: str = "", *, include_items: bool = True) -> dict[str, Any]:
        samples = self._calibration_samples(project_id, team_id)
        scope = "Team" if team_id and len(samples) >= 3 else "Project"
        if team_id and len(samples) < 3:
            samples = self._calibration_samples(project_id, "")
        if len(samples) < 3:
            return {
                "projectId": project_id, "teamId": team_id, "calibrationScope": "Uncalibrated",
                "sampleCount": len(samples), "accuracy": None, "bias": "Insufficient history",
                "message": "At least three completed outcomes are required for project or team calibration.",
                "samples": samples if include_items else [],
            }
        ratios = []
        absolute_errors = []
        for sample in samples:
            expected = _expected_days(int(sample["storyPoints"]))
            actual = float(sample["actualCycleTimeDays"])
            ratios.append(actual / expected)
            absolute_errors.append(abs(actual - expected) / max(actual, expected))
        ratio = median(ratios)
        accuracy = round(max(0.0, 100 * (1 - sum(absolute_errors) / len(absolute_errors))), 1)
        bias = "Underestimating" if ratio > 1.2 else "Overestimating" if ratio < .8 else "Balanced"
        return {
            "projectId": project_id, "teamId": team_id, "calibrationScope": scope,
            "sampleCount": len(samples), "accuracy": accuracy, "bias": bias,
            "cycleTimeBiasRatio": round(ratio, 2),
            "qualitySignals": {
                "reopens": sum(int(sample.get("reopenCount") or 0) for sample in samples),
                "prIterations": sum(int(sample.get("prIterations") or 0) for sample in samples),
                "escapedDefects": sum(int(sample.get("escapedDefects") or 0) for sample in samples),
            },
            "samples": samples if include_items else [],
        }

    def _calibration_samples(self, project_id: str, team_id: str) -> list[dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {}
        for estimate, outcome in self.estimates.project_outcomes(project_id, team_id):
            values[estimate.work_item_id] = {
                "estimateId": estimate.estimate_id, "workItemId": estimate.work_item_id,
                "storyPoints": estimate.story_points, "actualCycleTimeDays": outcome.get("actualCycleTimeDays"),
                "actualActiveTimeDays": outcome.get("actualActiveTimeDays"), "reopenCount": outcome.get("reopenCount", 0),
                "prIterations": outcome.get("prIterations", 0), "escapedDefects": outcome.get("escapedDefects", 0),
                "source": "HEI outcome feedback",
            }
        for key, item in self.ado_sdk.cached_collection(project_id, "workItems").items():
            item_team = str(item.get("teamId") or "")
            points = item.get("storyPoints") or item.get("effort")
            actual = _actual_cycle(item)
            if str(item.get("state") or "").lower() not in COMPLETED_STATES or points is None or actual is None:
                continue
            if team_id and item_team != team_id:
                continue
            values.setdefault(str(key), {
                "estimateId": "", "workItemId": str(key), "storyPoints": int(points),
                "actualCycleTimeDays": actual, "actualActiveTimeDays": item.get("actualActiveTimeDays"),
                "reopenCount": item.get("reopenCount", 0), "prIterations": item.get("prIterations", 0),
                "escapedDefects": item.get("escapedDefects", 0), "source": "Synchronized Azure DevOps history",
            })
        return list(values.values())

    def _resolve(self, work_item_id: str, project_id: str) -> tuple[dict[str, Any], str]:
        cached = self.ado_sdk.find_cached("workItems", str(work_item_id), project_id)
        if not cached:
            raise WorkItemNotFoundError(str(work_item_id))
        return dict(cached[1]), cached[0]

    def _historical(self, project_id: str, work_item_id: str) -> list[dict[str, Any]]:
        return [
            dict(item) for key, item in self.ado_sdk.cached_collection(project_id, "workItems").items()
            if str(key) != str(work_item_id) and str(item.get("state") or "").lower() in COMPLETED_STATES
        ]

    def _memory(self, project_id: str, item: dict[str, Any], repository_impact: dict[str, Any]) -> dict[str, Any]:
        if not self.engineering_memory:
            return {"matches": [], "count": 0, "role": "supporting_evidence"}
        try:
            result = self.engineering_memory.find_relevant_memory({
                "query": [item.get("title"), *_criteria(item.get("acceptanceCriteria"))],
                "modules": repository_impact.get("modules") or [], "artifactType": item.get("workItemType"),
                "tags": item.get("tags") or [], "limit": 5,
            })
        except (OSError, ValueError, TypeError):
            result = {"results": [], "count": 0}
        matches = [
            {"memoryId": value.get("id"), "title": value.get("title"), "score": value.get("searchScore"), "reason": value.get("matchReasons")}
            for value in result.get("results") or [] if str(value.get("projectId") or project_id) == project_id
        ]
        return {"matches": matches, "count": len(matches), "role": "supporting_evidence"}

    def _mark_stale(self, estimate: EstimationRecommendation) -> None:
        cached = self.ado_sdk.find_cached("workItems", estimate.work_item_id, estimate.project_id)
        if cached and int(cached[1].get("revision") or 0) != estimate.work_item_revision:
            estimate.status = EstimationStatus.STALE
            self.estimates.save(estimate)

    def _active(self, estimate_id: str) -> EstimationRecommendation:
        estimate = self.estimates.get(estimate_id)
        if not estimate:
            raise RecommendationNotFoundError(estimate_id)
        self._mark_stale(estimate)
        if estimate.status == EstimationStatus.STALE:
            raise StaleRecommendationError(estimate_id)
        return estimate

    def _event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({
                "eventType": event_type, "source": "ADOEstimationIntelligence",
                "projectId": payload.get("projectId"), "correlationId": payload.get("correlationId"),
                "payload": payload,
            })


def _criteria(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    text = re.sub(r"</(?:li|p|div|br)>", "\n", str(value or ""), flags=re.I)
    return [line.strip(" -;\t") for line in _clean(text).split("\n") if line.strip(" -;\t")]


def _clean(value: Any) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def _strings(value: Any) -> list[str]:
    if not value:
        return []
    values = value if isinstance(value, list) else [value]
    result = []
    for item in values:
        text = item.get("title") or item.get("name") or item.get("description") if isinstance(item, dict) else item
        if _clean(text):
            result.append(_clean(text))
    return list(dict.fromkeys(result))


def _repository_impact(request: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    supplied = request.get("repositoryImpact") if isinstance(request.get("repositoryImpact"), dict) else {}
    modules = _strings(supplied.get("modules")); files = _strings(supplied.get("files"))
    for evidence in analysis.get("evidence") or []:
        if not isinstance(evidence, dict):
            continue
        value = evidence.get("name") or evidence.get("title") or evidence.get("path") or evidence.get("value")
        kind = str(evidence.get("type") or evidence.get("category") or "").lower()
        if "module" in kind and value: modules.append(_clean(value))
        if "file" in kind and value: files.append(_clean(value))
    mode = str(supplied.get("mode") or (analysis.get("context") or {}).get("repositoryMode") or "Unavailable")
    return {"mode": mode, "modules": list(dict.fromkeys(modules)), "files": list(dict.fromkeys(files)), "crossModule": len(set(modules)) >= 3}


def _dependencies(request: dict[str, Any], analysis: dict[str, Any], item: dict[str, Any]) -> list[dict[str, Any]]:
    values = _strings(request.get("dependencies") or analysis.get("dependencies"))
    for link in item.get("links") or []:
        if not isinstance(link, dict): continue
        relation = str(link.get("relation") or link.get("rel") or "").lower()
        if any(term in relation for term in ("dependency", "predecessor", "successor")):
            values.append(str(link.get("targetId") or link.get("target_id") or link.get("targetUrl") or ""))
    return [{"name": value, "status": "NeedsValidation", "source": "ADO or approved analysis"} for value in dict.fromkeys(value for value in values if value)]


def _similar_items(item: dict[str, Any], historical: list[dict[str, Any]], impact: dict[str, Any]) -> list[dict[str, Any]]:
    target = _tokens(f"{item.get('title', '')} {item.get('description', '')} {' '.join(impact.get('modules') or [])}")
    result = []
    for candidate in historical:
        tokens = _tokens(f"{candidate.get('title', '')} {candidate.get('description', '')}")
        score = len(target & tokens) / max(1, len(target | tokens))
        if score < .1: continue
        result.append({
            "workItemId": str(candidate.get("workItemId") or ""), "title": candidate.get("title") or "",
            "storyPoints": candidate.get("storyPoints") or candidate.get("effort"),
            "actualCycleTimeDays": _actual_cycle(candidate), "similarity": round(score, 2),
            "reason": "Shared requirement and repository terms.",
        })
    return sorted(result, key=lambda value: value["similarity"], reverse=True)[:5]


def _tokens(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 2}


def _story_points(item: dict[str, Any], criteria: list[str], decomposition: list[str], impact: dict[str, Any], dependencies: list[dict[str, Any]], similar: list[dict[str, Any]], calibration: dict[str, Any]) -> int:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    if any(term in text for term in ("documentation", "readme", "copy change", "typo")) and len(criteria) <= 2:
        return 1
    score = 1 + min(4, len(criteria)) + min(2, len(decomposition) // 2) + min(3, len(impact.get("modules") or [])) + min(2, len(impact.get("files") or []) // 3) + min(2, len(dependencies))
    points = 1 if score <= 2 else 2 if score <= 4 else 3 if score <= 6 else 5 if score <= 9 else 8 if score <= 12 else 13
    historical_points = [int(value["storyPoints"]) for value in similar if value.get("storyPoints") in POINTS]
    if historical_points:
        historical = min(POINTS, key=lambda value: abs(value - median(historical_points)))
        points = max(points, historical) if impact.get("crossModule") else min(POINTS, key=lambda value: abs(value - (points + historical) / 2))
    if impact.get("crossModule"):
        points = max(points, 8)
    ratio = calibration.get("cycleTimeBiasRatio")
    index = POINTS.index(points)
    if isinstance(ratio, (int, float)) and ratio > 1.25 and index < len(POINTS) - 1: points = POINTS[index + 1]
    elif isinstance(ratio, (int, float)) and ratio < .75 and index > 0: points = POINTS[index - 1]
    return points


def _uncertainty(criteria: list[str], impact: dict[str, Any], historical: list[dict[str, Any]], similar: list[dict[str, Any]], dependencies: list[dict[str, Any]], request: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if not criteria: reasons.append("Acceptance criteria are missing.")
    if impact.get("mode") == "Unavailable": reasons.append("Repository impact is unavailable.")
    elif not impact.get("modules") and not impact.get("files"): reasons.append("Repository impact has not identified modules or files.")
    if not historical: reasons.append("No completed project history is available.")
    elif not similar: reasons.append("No sufficiently similar completed work was found.")
    if dependencies: reasons.append("Dependencies require validation before commitment.")
    if not isinstance(request.get("teamConfig"), dict): reasons.append("Team capacity configuration was not supplied.")
    level = "High" if len(reasons) >= 4 else "Medium" if reasons else "Low"
    return {"level": level, "reasons": reasons}


def _confidence(criteria: list[str], impact: dict[str, Any], similar: list[dict[str, Any]], calibration: dict[str, Any], uncertainty: dict[str, Any]) -> float:
    value = .35 + min(.2, len(criteria) * .04)
    if impact.get("mode") != "Unavailable": value += .12
    if impact.get("modules") or impact.get("files"): value += .08
    if similar: value += .1
    if calibration.get("calibrationScope") != "Uncalibrated": value += .1
    value -= {"High": .15, "Medium": .06, "Low": 0}.get(uncertainty.get("level"), .05)
    return round(max(.2, min(.95, value)), 2)


def _tasks(item: dict[str, Any], criteria: list[str], decomposition: list[str], impact: dict[str, Any], memory: dict[str, Any]) -> list[dict[str, Any]]:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    if any(term in text for term in ("documentation", "readme", "copy change", "typo")):
        return [
            {"title": "Update the affected documentation", "workArea": "Documentation", "acceptanceCriteria": criteria[:2]},
            {"title": "Verify links, examples, and terminology", "workArea": "QA", "acceptanceCriteria": criteria[:2]},
            {"title": "Review the documentation change", "workArea": "Review", "acceptanceCriteria": criteria[:2]},
        ]
    values = []
    for criterion in criteria[:4]:
        work_area = _area(criterion)
        values.append({"title": _task_title(criterion, work_area), "workArea": work_area, "acceptanceCriteria": [criterion]})
    for entry in decomposition[:2]:
        values.append({"title": entry, "workArea": _area(entry), "acceptanceCriteria": criteria[:2]})
    if impact.get("modules"):
        values.append({"title": f"Integrate affected modules: {', '.join(impact['modules'][:3])}", "workArea": "Integration", "acceptanceCriteria": criteria[:3]})
    values.append({"title": "Add acceptance, negative, and regression tests", "workArea": "QA", "acceptanceCriteria": criteria[:5]})
    values.append({"title": "Review implementation scope and evidence", "workArea": "Review", "acceptanceCriteria": criteria[:5]})
    unique = []; seen = set()
    for value in values:
        key = value["title"].lower()
        if key not in seen:
            seen.add(key); unique.append(value)
    if len(unique) < 3:
        unique.insert(0, {"title": f"Implement {item.get('title') or 'the approved outcome'}", "workArea": "Engineering", "acceptanceCriteria": criteria})
    return unique[:8]


def _area(value: str) -> str:
    text = value.lower()
    if any(term in text for term in ("screen", "view", "display", "ui")): return "UI"
    if any(term in text for term in ("api", "service", "endpoint")): return "Backend"
    if any(term in text for term in ("data", "database", "query")): return "Data"
    if any(term in text for term in ("test", "validate", "error")): return "QA"
    return "Engineering"


def _task_title(criterion: str, work_area: str) -> str:
    outcome = re.sub(r"^(the )?(user|operator|technician) (can|must|should)\s+", "", criterion.strip(), flags=re.I)
    outcome = outcome.rstrip(".")
    words = outcome.split()[:12]
    concise = " ".join(words) or "the approved acceptance outcome"
    verb = {"UI": "Build", "Backend": "Add", "Data": "Map", "QA": "Validate"}.get(work_area, "Deliver")
    return f"{verb} {concise[0].lower() + concise[1:] if concise else concise}"


def _blockers(criteria: list[str], impact: dict[str, Any], dependencies: list[dict[str, Any]], request: dict[str, Any]) -> list[str]:
    result = []
    if not criteria: result.append("Acceptance criteria are required before commitment.")
    if impact.get("mode") == "Unavailable": result.append("Repository impact must be reviewed manually.")
    if dependencies: result.append("Dependency ownership and sequencing require validation.")
    config = request.get("teamConfig") if isinstance(request.get("teamConfig"), dict) else {}
    if config.get("availableCapacityDays") is not None and float(config["availableCapacityDays"]) <= 0:
        result.append("Team capacity is unavailable for the selected iteration.")
    return result


def _evidence(criteria: list[str], impact: dict[str, Any], similar: list[dict[str, Any]], memory: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    values = [{"type": "AcceptanceCriteria", "value": item, "source": "Azure DevOps"} for item in criteria[:5]]
    values += [{"type": "Module", "value": item, "source": "Repository Intelligence"} for item in impact.get("modules") or []]
    values += [{"type": "File", "value": item, "source": "Repository Intelligence"} for item in impact.get("files") or []]
    values += [{"type": "HistoricalWork", "value": item.get("workItemId"), "source": "Azure DevOps synchronized history"} for item in similar]
    values += [{"type": "EngineeringMemory", "value": item.get("memoryId"), "source": "Approved Engineering Memory"} for item in memory.get("matches") or []]
    return values + [item for item in analysis.get("evidence") or [] if isinstance(item, dict)][:5]


def _actual_cycle(item: dict[str, Any]) -> float | None:
    if item.get("actualCycleTimeDays") is not None:
        return float(item["actualCycleTimeDays"])
    start = _date(item.get("createdAt")); end = _date(item.get("closedAt") or item.get("stateChangeDate"))
    return round((end - start).total_seconds() / 86400, 1) if start and end and end >= start else None


def _date(value: Any) -> datetime | None:
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError: return None


def _optional_positive(value: Any, name: str) -> float | None:
    if value in (None, ""): return None
    try: result = float(value)
    except (TypeError, ValueError) as error: raise ValueError(f"{name} must be numeric.") from error
    if result < 0: raise ValueError(f"{name} cannot be negative.")
    return result


def _expected_days(points: int) -> float:
    return {1: .75, 2: 1.5, 3: 2.5, 5: 3, 8: 5.5, 13: 9.5}.get(points, 3)
