"""Deterministic Planning Recommendation Engine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.platform.shared import JsonMapStore
from backend.reasoning import ReasoningEngine

from .models import (
    PlanningRecommendation,
    RecommendationAlternative,
    RecommendationConfidence,
    RecommendationDiff,
    RecommendationImpact,
    RecommendationReason,
    RecommendationStrategy,
    RecommendationSummary,
)


class PlanningRecommendationService:
    """Selects and explains a strategy from a completed Planning Context."""

    def __init__(
        self,
        store: JsonMapStore,
        *,
        planning_context_service: Any,
        engineering_intelligence: Any | None = None,
        reasoning_engine: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.planning_context_service = planning_context_service
        self.engineering_intelligence = engineering_intelligence
        self.reasoning_engine = reasoning_engine or ReasoningEngine()
        self.platform = platform

    def build(self, request: dict[str, Any]) -> dict[str, Any]:
        context_id = _required(request, "contextId")
        context = self.planning_context_service.get(context_id)
        context = self.planning_context_service.require_reviewed(context_id, _text(context.get("requirementId")))
        canonical_context = _canonical_engineering_context(context)
        context = self._engineering_context(context)
        values = self.store.read()
        existing = _for_context(values, context_id)
        if existing and request.get("force") is not True:
            return existing
        version = int((existing or {}).get("version") or 0) + 1
        strategy, scores = _select_strategy(context)
        reasoning_result = self._reason(
            canonical_context or _canonical_engineering_context(context),
            request,
        )
        strategy = _reasoned_strategy(reasoning_result, strategy)
        scores[strategy] = max(scores.get(strategy, 0), _reasoning_confidence(reasoning_result))
        record = self._assemble(
            context, strategy, scores, version, existing, reasoning_result,
        )
        values[record["recommendationId"]] = record
        self.store.write(values)
        self._publish("PlanningRecommendationCreated", record)
        return record

    def get(self, recommendation_id: str) -> dict[str, Any]:
        record = self.store.read().get(recommendation_id)
        if not isinstance(record, dict):
            raise LookupError("Planning Recommendation was not found.")
        return record

    def regenerate(self, request: dict[str, Any]) -> dict[str, Any]:
        recommendation_id = _text(request.get("recommendationId"))
        if recommendation_id:
            current = self.get(recommendation_id)
            context_id = current["contextId"]
        else:
            context_id = _required(request, "contextId")
        return self.build({**request, "contextId": context_id, "force": True})

    def approve(self, request: dict[str, Any]) -> dict[str, Any]:
        recommendation_id = _required(request, "recommendationId")
        actor = _required(request, "actor")
        values = self.store.read()
        record = self.get(recommendation_id)
        self.planning_context_service.require_reviewed(record["contextId"], record["requirementId"])
        record["status"] = "Approved"
        record["approvedBy"] = actor
        record["approvedAt"] = _now()
        approval = {
            "action": "Approved", "actor": actor, "at": record["approvedAt"],
            "strategy": record["strategy"], "comments": _text(request.get("comments")),
        }
        record["history"] = list(record.get("history") or []) + [approval]
        record["approvalHistory"] = list(record.get("approvalHistory") or []) + [approval]
        values[recommendation_id] = record
        self.store.write(values)
        self._publish("PlanningRecommendationApproved", record)
        return record

    def override(self, request: dict[str, Any]) -> dict[str, Any]:
        recommendation_id = _required(request, "recommendationId")
        actor = _required(request, "actor")
        strategy = _strategy(_required(request, "strategy"))
        reason = _required(request, "reason")
        values = self.store.read()
        current = self.get(recommendation_id)
        context = self.planning_context_service.require_reviewed(current["contextId"], current["requirementId"])
        context = self._engineering_context(context)
        scores = {item.value: 20 for item in RecommendationStrategy}
        scores[strategy] = 100
        reasoning_result = self._reason(
            _canonical_engineering_context(context),
            {**request, "providerPreference": "Deterministic"},
        )
        record = self._assemble(
            context, strategy, scores, int(current.get("version") or 1) + 1,
            current, reasoning_result,
        )
        record["overrideReason"] = reason
        change = {
            "action": "StrategyOverridden", "actor": actor, "at": _now(),
            "from": current.get("strategy"), "to": strategy, "reason": reason,
        }
        record["history"] = list(current.get("history") or []) + [change]
        record["userChanges"] = list(current.get("userChanges") or []) + [change]
        values[recommendation_id] = record
        self.store.write(values)
        self._publish("PlanningRecommendationOverridden", record)
        return record

    def require_approved(self, recommendation_id: str, context_id: str) -> dict[str, Any]:
        if not recommendation_id:
            raise ValueError("An approved Planning Recommendation is required before Planning Proposal generation.")
        record = self.get(recommendation_id)
        if record.get("contextId") != context_id:
            raise ValueError("Planning Recommendation does not belong to the reviewed Planning Context.")
        context = self.planning_context_service.get(context_id)
        if record.get("contextVersion") != context.get("contextVersion"):
            raise ValueError("Planning Recommendation is stale. Regenerate it from the current Planning Context.")
        if record.get("status") != "Approved":
            raise ValueError("Approve the Planning Recommendation before generating a Planning Proposal.")
        return record

    def get_alternatives(self, recommendation_id: str) -> dict[str, Any]:
        record = self.get(recommendation_id)
        return {
            "recommendationId": recommendation_id,
            "primaryRecommendation": record.get("primaryRecommendation") or {},
            "alternatives": list(record.get("alternatives") or []),
            "strategyOptions": list(record.get("strategyOptions") or []),
        }

    def calculate_readiness(self, request: dict[str, Any]) -> dict[str, Any]:
        record, context = self._record_and_context(request)
        readiness = _recommendation_readiness(context)
        if record is not None:
            readiness["recommendationId"] = record["recommendationId"]
        return readiness

    def calculate_impact(self, request: dict[str, Any]) -> dict[str, Any]:
        record, context = self._record_and_context(request)
        impact = _engineering_impact_summary(context)
        if record is not None:
            impact["recommendationId"] = record["recommendationId"]
        return impact

    def get_reuse_suggestions(self, request: dict[str, Any]) -> dict[str, Any]:
        record, context = self._record_and_context(request)
        suggestions = _reuse_suggestions(context)
        return {
            "recommendationId": (record or {}).get("recommendationId", ""),
            "suggestions": suggestions,
            "count": len(suggestions),
        }

    def export_report(self, recommendation_id: str) -> dict[str, Any]:
        record = self.get(recommendation_id)
        return {
            "schemaVersion": "hei-planning-recommendation-report-v1",
            "recommendation": record,
            "exportedAt": _now(),
            "notice": "This report contains recommendations only. No Azure DevOps work item was created or modified.",
        }

    generateRecommendation = build
    getAlternatives = get_alternatives
    calculateReadiness = calculate_readiness
    calculateImpact = calculate_impact
    getReuseSuggestions = get_reuse_suggestions

    def to_engine_recommendation(self, record: dict[str, Any]) -> dict[str, Any]:
        mode_map = {
            "NEW_EPIC": "NEW_INITIATIVE",
            "NEW_INITIATIVE": "NEW_INITIATIVE",
            "NEW_FEATURE": "NEW_FEATURE",
            "NEW_STORY": "EXTEND_FEATURE",
            "EXTEND_EXISTING_FEATURE": "EXTEND_FEATURE",
            "EXTEND_EXISTING_EPIC": "NEW_FEATURE",
            "EXTEND_EXISTING_STORY": "MODIFY_EXISTING",
            "MODIFY_EXISTING_STORY": "MODIFY_EXISTING",
            "BUG_FIX": "BUG_OR_ENHANCEMENT",
            "ENHANCEMENT": "BUG_OR_ENHANCEMENT",
            "TECHNICAL_DEBT": "MODIFY_EXISTING",
            "REFACTOR": "MODIFY_EXISTING",
            "REFACTOR_EXISTING_FEATURE": "MODIFY_EXISTING",
            "SPIKE": "AI_RECOMMENDED",
            "CONFIGURATION_CHANGE": "MODIFY_EXISTING",
            "DOCUMENTATION_UPDATE": "MODIFY_EXISTING",
            "MIXED_RECOMMENDATION": "AI_RECOMMENDED",
            "AI_RECOMMENDED": "AI_RECOMMENDED",
        }
        return {
            "schemaVersion": "hei-planning-recommendation-adapter-v1",
            "contextId": record["contextId"],
            "mode": mode_map.get(record["strategy"], "AI_RECOMMENDED"),
            "confidence": int(record.get("confidence", {}).get("overall") or 0),
            "reason": [item.get("explanation") for item in record.get("reasons", [])],
            "existingItems": [
                item.get("workItem") or {
                    "id": item.get("workItemId"), "type": item.get("workItemType"),
                    "title": item.get("title"), "state": item.get("state"),
                }
                for item in record.get("similarWork", [])
            ],
            "repositoryMatch": {
                "repositoryId": record.get("impact", {}).get("repositoryId"),
                "confidence": int(record.get("confidence", {}).get("repository") or 0),
            },
            "memorySuggestions": [],
            "recommendedStrategy": {
                "description": record.get("engineeringReasoning", [""])[0],
                "allowedActions": _allowed_actions(record["strategy"]),
            },
            "requiresHumanApproval": True,
            "generatedAt": record.get("generatedAt"),
        }

    def _engineering_context(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.engineering_intelligence:
            return context
        return self.engineering_intelligence.from_planning_context(context)

    def _reason(
        self,
        engineering_context: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self.reasoning_engine.recommend(
            "Planning Recommendation",
            engineering_context,
            provider=_text(request.get("providerPreference") or request.get("provider")) or "Auto",
            correlation_id=_text(engineering_context.get("correlationId")),
        )

    def _record_and_context(
        self, request: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        recommendation_id = _text(request.get("recommendationId"))
        record = self.get(recommendation_id) if recommendation_id else None
        context_id = _text(request.get("contextId")) or _text((record or {}).get("contextId"))
        if not context_id:
            raise ValueError("recommendationId or contextId is required.")
        context = self.planning_context_service.get(context_id)
        context = self.planning_context_service.require_reviewed(
            context_id, _text(context.get("requirementId")),
        )
        return record, self._engineering_context(context)

    def _assemble(
        self,
        context: dict[str, Any],
        strategy: str,
        scores: dict[str, int],
        version: int,
        existing: dict[str, Any] | None,
        reasoning_result: dict[str, Any],
    ) -> dict[str, Any]:
        repository = context.get("repository") or {}
        memory = context.get("memory") or {}
        impact_context = context.get("impact") or {}
        requirement = context.get("requirement") or {}
        similar = list(context.get("similarWork") or [])
        related_pull_requests = list(context.get("azureDevOps", {}).get("openPullRequests") or [])
        current_development = list(context.get("azureDevOps", {}).get("currentDevelopment") or [])
        overall = max(35, min(98, int(scores.get(strategy) or 0)))
        confidence = RecommendationConfidence(
            engineering=overall,
            repository=int(repository.get("confidence") or 0),
            memory=int(memory.get("coverage") or 0),
            planning=int(context.get("readiness", {}).get("score") or 0),
            overall=round(
                overall * 0.4
                + int(repository.get("confidence") or 0) * 0.25
                + int(memory.get("coverage") or 0) * 0.1
                + int(context.get("readiness", {}).get("score") or 0) * 0.25
            ),
        )
        actions = _actions(strategy, context)
        diff = _recommendation_diff(context, actions)
        alternatives = _alternatives(
            strategy, scores, context=context, reasoning_result=reasoning_result,
        )
        risks = _unique(
            list(impact_context.get("potentialRisks") or [])
            + list(impact_context.get("potentialBreakingChanges") or [])
            + (["Open pull requests overlap the current engineering landscape. Review planned changes against active development."] if related_pull_requests else [])
        )
        reasoning = _reasoning(strategy, context, alternatives)
        provider_reasoning = _strings(reasoning_result.get("reasoning"))
        if provider_reasoning:
            reasoning = _unique(provider_reasoning + reasoning)
        reasons = [
            RecommendationReason(
                title="Existing engineering landscape",
                explanation=reasoning[0],
                evidence=[
                    f"{len(similar)} similar synchronized work items",
                    f"{repository.get('reusePercent', 0)}% repository reuse",
                    f"{memory.get('coverage', 0)}% Engineering Memory coverage",
                ],
                confidence=confidence.engineering,
            ),
            RecommendationReason(
                title="Implementation boundary",
                explanation=reasoning[1],
                evidence=_unique(list(repository.get("affectedModules") or []) + list(repository.get("affectedApis") or []))[:8],
                confidence=confidence.repository,
            ),
        ]
        rejected = [
            RecommendationReason(
                title=alternative.title,
                explanation=alternative.rejectedReason,
                evidence=alternative.cons,
                confidence=alternative.confidence,
            )
            for alternative in alternatives
        ]
        affected_docs = ["Planning and operational documentation"] if requirement.get("nonFunctionalRequirements") else []
        recommendation_impact = RecommendationImpact(
            repositoryId=_text(repository.get("repositoryId")),
            repositoryName=_text(repository.get("repositoryName")),
            businessImpact=_business_impact(strategy, requirement),
            engineeringImpact=_engineering_impact(strategy, context),
            repositoryImpact=_repository_impact(repository),
            sprintImpact=_text(impact_context.get("sprintImpact")) or "Review during Planning Proposal estimation.",
            estimatedComplexity=_text(impact_context.get("complexity")) or "Medium",
            affectedModules=list(repository.get("affectedModules") or []),
            affectedStories=list(impact_context.get("affectedStories") or []),
            affectedFeatures=list(impact_context.get("affectedFeatures") or []),
            affectedApis=list(repository.get("affectedApis") or []),
            affectedServices=list(repository.get("affectedServices") or []),
            affectedScreens=list(repository.get("affectedScreens") or []),
            affectedTests=list(repository.get("reusableTests") or []),
            affectedDocumentation=affected_docs,
            riskLevel=_text(context.get("summary", {}).get("engineeringRisk")) or "Medium",
        )
        expected_stories = max(1, len(requirement.get("functionalRequirements") or []))
        expected_tasks = expected_stories * (3 if recommendation_impact.estimatedComplexity == "High" else 2)
        expected_modifications = sum(1 for item in diff.operations if item.get("action") == "Modify")
        current_sprint = context.get("azureDevOps", {}).get("currentSprint") or {}
        summary = RecommendationSummary(
            recommendedStrategy=strategy,
            engineeringConfidence=confidence.engineering,
            repositoryConfidence=confidence.repository,
            memoryConfidence=confidence.memory,
            planningConfidence=confidence.planning,
            expectedSprint=_text(current_sprint.get("name") or current_sprint.get("path")) or "Planning decision required",
            expectedStoryCount=expected_stories,
            expectedTaskCount=expected_tasks,
            expectedModificationCount=expected_modifications,
        )
        recommendation_id = _text((existing or {}).get("recommendationId")) or "planning-recommendation-" + _digest(context["contextId"])
        primary = _strategy_option(
            strategy,
            confidence.overall,
            context,
            description=reasoning[0],
            selected=True,
        )
        provider_recommendation = reasoning_result.get("recommendation") or {}
        if isinstance(provider_recommendation, dict) and _text(provider_recommendation.get("strategy")).upper() == strategy:
            primary["description"] = _text(provider_recommendation.get("description")) or primary["description"]
            primary["estimatedEffort"] = _text(provider_recommendation.get("estimatedEffort")) or primary["estimatedEffort"]
            primary["risks"] = _strings(provider_recommendation.get("risks")) or primary["risks"]
            if provider_recommendation.get("reuseScore") is not None:
                primary["reuseScore"] = max(0, min(100, int(provider_recommendation["reuseScore"])))
        strategy_options = [primary] + [
            _alternative_option(item) for item in alternatives
        ]
        repository_analysis = _repository_analysis(context)
        existing_work = _existing_work_detection(context)
        reuse_suggestions = _reuse_suggestions(context)
        dependency_analysis = _dependency_analysis(context)
        engineering_impact = _engineering_impact_summary(context)
        readiness = _recommendation_readiness(context)
        missing_information = _missing_information(context)
        explanation = _recommendation_explanation(
            strategy, reasoning, alternatives, reasoning_result, context,
        )
        record = PlanningRecommendation(
            recommendationId=recommendation_id,
            contextId=context["contextId"],
            contextVersion=context["contextVersion"],
            requirementId=context["requirementId"],
            projectId=_text(context.get("projectId")),
            correlationId=_text(context.get("correlationId")),
            strategy=strategy,
            title=_strategy_title(strategy),
            status="PendingReview",
            version=version,
            confidence=confidence,
            reasons=reasons,
            rejectedAlternatives=rejected,
            alternatives=alternatives,
            actions=actions,
            similarWork=similar,
            relatedPullRequests=related_pull_requests,
            currentDevelopment=current_development,
            repositoryComponents=_unique(list(repository.get("reusableComponents") or []) + list(repository.get("reusableTests") or [])),
            dependencies=_strings(requirement.get("dependencies")),
            architectureDecisions=list(memory.get("architectureDecisions") or []),
            impact=recommendation_impact,
            diff=diff,
            summary=summary,
            risks=risks,
            engineeringReasoning=reasoning,
            expectedRepositoryImpact=recommendation_impact.repositoryImpact,
            expectedAzureDevOpsImpact=_ado_impact(actions),
            generatedAt=_now(),
            history=list((existing or {}).get("history") or []),
            reasoningVersion=_text(reasoning_result.get("promptVersion")).split(":")[0],
            promptVersion=_text(reasoning_result.get("promptVersion")),
            reasoningMode=_text(reasoning_result.get("reasoningMode")) or "Deterministic",
            reasoningResult=_bounded_reasoning_result(reasoning_result),
            primaryRecommendation=primary,
            strategyOptions=strategy_options,
            repositoryAnalysis=repository_analysis,
            existingWorkDetection=existing_work,
            reuseSuggestions=reuse_suggestions,
            dependencyAnalysis=dependency_analysis,
            engineeringImpact=engineering_impact,
            readiness=readiness,
            missingInformation=missing_information,
            explanation=explanation,
            userChanges=list((existing or {}).get("userChanges") or []),
            approvalHistory=list((existing or {}).get("approvalHistory") or []),
        )
        return record.to_dict()

    def _publish(self, event_type: str, record: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "PlanningRecommendationEngine",
            "projectId": record.get("projectId"),
            "correlationId": record.get("correlationId"),
            "payload": {
                "recommendationId": record.get("recommendationId"),
                "contextId": record.get("contextId"),
                "strategy": record.get("strategy"),
                "status": record.get("status"),
            },
        })


def _select_strategy(context: dict[str, Any]) -> tuple[str, dict[str, int]]:
    requirement = context.get("requirement") or {}
    text = " ".join([
        _text(requirement.get("title")), _text(requirement.get("planningRequirement")),
        " ".join(_strings(requirement.get("functionalRequirements"))),
    ]).casefold()
    classification = _text(context.get("classification", {}).get("value"))
    similar = list(context.get("similarWork") or [])
    best = similar[0] if similar else {}
    best_type = _text(best.get("workItemType"))
    best_score = int(best.get("similarity") or 0)
    scores = {item.value: 20 for item in RecommendationStrategy}
    scores["AI_RECOMMENDED"] = 45
    if classification == "NEW_INITIATIVE":
        scores["NEW_INITIATIVE"] = 92
    if classification == "NEW_FEATURE":
        scores["NEW_FEATURE"] = 88
    if classification == "ENHANCEMENT":
        scores["ENHANCEMENT"] = 90
    if classification == "BUG" or any(term in text for term in ("bug", "defect", "fix error", "regression")):
        scores["BUG_FIX"] = 95
    if any(term in text for term in ("technical debt", "debt reduction", "legacy cleanup")):
        scores["TECHNICAL_DEBT"] = 94
    if any(term in text for term in ("refactor", "restructure", "preserve behavior")):
        scores["REFACTOR_EXISTING_FEATURE"] = 94
    if any(term in text for term in ("spike", "investigate", "proof of concept", "prototype", "feasibility")):
        scores["SPIKE"] = 93
    if any(term in text for term in ("configuration", "config change", "feature flag", "settings only")):
        scores["CONFIGURATION_CHANGE"] = 94
    if any(term in text for term in ("documentation", "docs only", "readme", "runbook")):
        scores["DOCUMENTATION_UPDATE"] = 94
    if best_score >= 78 and best_type == "Story":
        scores["MODIFY_EXISTING_STORY"] = max(scores["MODIFY_EXISTING_STORY"], 92)
    if best_score >= 55 and best_type == "Feature":
        scores["EXTEND_EXISTING_FEATURE"] = max(scores["EXTEND_EXISTING_FEATURE"], 90)
    if best_score >= 55 and best_type == "Epic":
        scores["EXTEND_EXISTING_EPIC"] = max(scores["EXTEND_EXISTING_EPIC"], 88)
    strategy = max(scores, key=scores.get)
    return strategy, scores


def _reasoned_strategy(reasoning_result: dict[str, Any], fallback: str) -> str:
    if _text(reasoning_result.get("reasoningMode")) != "AI":
        return fallback
    structured = reasoning_result.get("structuredResponse") or {}
    recommendation = structured.get("recommendation") or reasoning_result.get("recommendation") or {}
    proposed = recommendation.get("strategy") if isinstance(recommendation, dict) else ""
    confidence = reasoning_result.get("confidence") or {}
    overall = confidence.get("overall") if isinstance(confidence, dict) else confidence
    if _is_strategy(proposed) and int(overall or 0) >= 55:
        return _strategy(_text(proposed))
    return fallback


def _reasoning_confidence(reasoning_result: dict[str, Any]) -> int:
    confidence = reasoning_result.get("confidence") or {}
    value = confidence.get("overall") if isinstance(confidence, dict) else confidence
    return max(0, min(100, int(value or 0)))


def _actions(strategy: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    similar_work = list(context.get("similarWork") or [])
    if similar_work and int(similar_work[0].get("similarity") or 0) >= 95 and _text(similar_work[0].get("state")).casefold() in {"done", "closed", "completed"}:
        return [{"action": "Do Nothing", "confidence": 82, "reason": "A completed work item already satisfies nearly all of the approved requirement."}]
    primary = {
        "NEW_EPIC": "Create New Epic",
        "NEW_INITIATIVE": "Create New Epic",
        "NEW_FEATURE": "Create New Feature",
        "NEW_STORY": "Create Stories",
        "EXTEND_EXISTING_FEATURE": "Create Stories",
        "EXTEND_EXISTING_EPIC": "Create New Feature",
        "EXTEND_EXISTING_STORY": "Modify Existing Story",
        "MODIFY_EXISTING_STORY": "Modify Existing Story",
        "BUG_FIX": "Create Bug",
        "ENHANCEMENT": "Create Stories",
        "TECHNICAL_DEBT": "Create Tasks",
        "REFACTOR": "Create Tasks",
        "REFACTOR_EXISTING_FEATURE": "Create Tasks",
        "SPIKE": "Create Spike",
        "CONFIGURATION_CHANGE": "Create Tasks",
        "DOCUMENTATION_UPDATE": "Create Tasks",
        "MIXED_RECOMMENDATION": "Create Stories",
        "AI_RECOMMENDED": "Create Stories",
    }[strategy]
    confidence = int(context.get("summary", {}).get("planningConfidence") or 60)
    actions = [{"action": primary, "confidence": confidence, "reason": _action_reason(strategy)}]
    repository = context.get("repository") or {}
    if repository.get("reusableComponents") or repository.get("reusableTests"):
        actions.append({"action": "Reuse Existing Components", "confidence": int(repository.get("confidence") or 0), "reason": "Repository Intelligence found relevant reusable engineering assets."})
    if strategy == "MODIFY_EXISTING_STORY" and len(context.get("requirement", {}).get("functionalRequirements") or []) > 5:
        actions.append({"action": "Split Story", "confidence": 72, "reason": "The requested behavior contains several independently testable outcomes."})
    strong_stories = [
        item for item in context.get("similarWork") or []
        if item.get("workItemType") == "Story" and int(item.get("similarity") or 0) >= 78
    ]
    if len(strong_stories) > 1:
        actions.append({"action": "Merge Story", "confidence": 68, "reason": "Multiple existing Stories overlap the same approved outcome."})
    return actions


def _recommendation_diff(context: dict[str, Any], actions: list[dict[str, Any]]) -> RecommendationDiff:
    operations: list[dict[str, Any]] = []
    primary = actions[0]["action"]
    requirement = context.get("requirement") or {}
    title = _text(requirement.get("title")) or "Requirement"
    if primary == "Create New Epic":
        operations.append(_operation("Create", "Epic", title, actions[0]["reason"], actions[0]["confidence"]))
    elif primary == "Create New Feature":
        operations.append(_operation("Create", "Feature", title, actions[0]["reason"], actions[0]["confidence"]))
    elif primary == "Create Bug":
        operations.append(_operation("Create", "Bug", title, actions[0]["reason"], actions[0]["confidence"]))
    elif primary == "Create Spike":
        operations.append(_operation("Create", "Spike", title, actions[0]["reason"], actions[0]["confidence"]))
    for item in list(context.get("similarWork") or [])[:10]:
        suggested = _text(item.get("suggestedAction"))
        action = "Modify" if suggested == "Modify" else "Reuse" if suggested == "Reuse" else "Ignore"
        operations.append(_operation(action, _text(item.get("workItemType")), _text(item.get("title")), _text(item.get("reason")), int(item.get("confidence") or 0)))
    if primary in {"Create Stories", "Create Tasks", "Modify Existing Story"}:
        for value in _strings(requirement.get("functionalRequirements"))[:8]:
            operations.append(_operation("Modify" if primary == "Modify Existing Story" else "Create", "Story", _short_title(value), "Derived from an approved functional requirement.", actions[0]["confidence"]))
    if any(item["action"] == "Split Story" for item in actions):
        operations.append(_operation("Split", "Story", title, "Separate independently valuable outcomes before task generation.", 72))
    if any(item["action"] == "Merge Story" for item in actions):
        operations.append(_operation("Merge", "Story", title, "Consolidate overlapping existing Stories before task generation.", 68))
    if any(item["action"] == "Do Nothing" for item in actions):
        operations.append(_operation("Ignore", "Requirement", title, "Existing completed work appears to satisfy the requested outcome.", 82))
    if any(item["action"] == "Reuse Existing Components" for item in actions):
        for value in _strings(context.get("repository", {}).get("reusableComponents"))[:6]:
            operations.append(_operation("Reuse", "Repository Component", value, "Repository evidence supports reuse.", int(context.get("repository", {}).get("confidence") or 0)))
    summary = {action: sum(1 for item in operations if item["action"] == action) for action in ("Create", "Modify", "Reuse", "Ignore", "Merge", "Split", "Delete", "Move")}
    return RecommendationDiff(
        diffId="recommendation-diff-" + _digest([context["contextId"], operations]),
        summary=summary,
        operations=operations,
    )


def _alternatives(
    selected: str,
    scores: dict[str, int],
    *,
    context: dict[str, Any],
    reasoning_result: dict[str, Any],
) -> list[RecommendationAlternative]:
    provider_alternatives = {
        _strategy(_text(item.get("strategy"))): item
        for item in reasoning_result.get("alternatives") or []
        if isinstance(item, dict) and _is_strategy(item.get("strategy"))
    }
    alternatives = []
    for strategy, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        if strategy == selected:
            continue
        provider_value = provider_alternatives.get(strategy) or {}
        alternatives.append(RecommendationAlternative(
            strategy=strategy,
            confidence=max(12, min(90, int(provider_value.get("confidence") or score))),
            title=_strategy_title(strategy),
            pros=_pros(strategy),
            cons=_cons(strategy),
            rejectedReason=f"{_strategy_title(selected)} better matches current backlog similarity, repository evidence, and requirement classification.",
            description=_text(provider_value.get("description")) or _action_reason(strategy),
            estimatedEffort=_text(provider_value.get("estimatedEffort")) or _estimated_effort(context, strategy),
            risks=_strings(provider_value.get("risks")) or _strategy_risks(strategy, context),
            reuseScore=_reuse_score(context, strategy),
        ))
        if len(alternatives) == 3:
            break
    return alternatives


def _reasoning(strategy: str, context: dict[str, Any], alternatives: list[RecommendationAlternative]) -> list[str]:
    similar = list(context.get("similarWork") or [])
    repository = context.get("repository") or {}
    best = similar[0] if similar else {}
    first = (
        f"{_strategy_title(strategy)} is the safest strategy because "
        + (f"{best.get('workItemType')} #{best.get('workItemId')} is {best.get('similarity')}% similar and " if best else "no strong duplicate work exists and ")
        + f"Repository Intelligence reports {repository.get('reusePercent', 0)}% reusable context."
    )
    second = (
        f"Changes should remain within {', '.join(repository.get('affectedModules') or ['the selected repository boundary'])}; "
        "unrelated modules and work items should remain unchanged."
    )
    third = "Alternatives were ranked lower because they either create a broader hierarchy than necessary or reuse less of the existing engineering landscape."
    if alternatives:
        third += f" The closest alternative is {alternatives[0].title} at {alternatives[0].confidence}% confidence."
    open_pull_requests = len(context.get("azureDevOps", {}).get("openPullRequests") or [])
    current_development = len(context.get("azureDevOps", {}).get("currentDevelopment") or [])
    fourth = f"The strategy was checked against {open_pull_requests} open pull request{'s' if open_pull_requests != 1 else ''} and {current_development} active work item{'s' if current_development != 1 else ''}."
    return [first, second, third, fourth]


def _strategy(value: str) -> str:
    normalized = value.strip().upper()
    valid = {item.value for item in RecommendationStrategy}
    if normalized not in valid:
        raise ValueError(f"strategy must be one of: {', '.join(sorted(valid))}.")
    return normalized


def _strategy_title(value: str) -> str:
    return value.replace("_", " ").title()


def _allowed_actions(strategy: str) -> list[str]:
    if strategy in {"MODIFY_EXISTING_STORY", "EXTEND_EXISTING_STORY", "TECHNICAL_DEBT", "REFACTOR", "REFACTOR_EXISTING_FEATURE", "CONFIGURATION_CHANGE", "DOCUMENTATION_UPDATE"}:
        return ["Modify", "Keep", "Split"]
    if strategy in {"EXTEND_EXISTING_FEATURE", "EXTEND_EXISTING_EPIC"}:
        return ["Keep", "Create", "Link"]
    return ["Create", "Link", "Keep"]


def _action_reason(strategy: str) -> str:
    return {
        "NEW_EPIC": "No existing Epic provides a sufficiently safe parent boundary.",
        "NEW_INITIATIVE": "No existing Epic provides a sufficiently safe parent boundary.",
        "NEW_FEATURE": "The requirement belongs in the current product but needs a distinct capability.",
        "NEW_STORY": "The requirement fits an existing Feature and needs a new independently valuable Story.",
        "EXTEND_EXISTING_FEATURE": "A synchronized Feature already owns this capability.",
        "EXTEND_EXISTING_EPIC": "A synchronized Epic is the correct parent for a new capability.",
        "EXTEND_EXISTING_STORY": "An existing Story can be safely extended without duplicating its outcome.",
        "MODIFY_EXISTING_STORY": "An existing Story already represents most of the requested behavior.",
        "BUG_FIX": "The requirement describes incorrect existing behavior.",
        "ENHANCEMENT": "The requirement expands an existing user outcome.",
        "TECHNICAL_DEBT": "The work primarily improves maintainability rather than product scope.",
        "REFACTOR": "The implementation should preserve behavior while changing structure.",
        "REFACTOR_EXISTING_FEATURE": "The existing Feature should preserve behavior while its implementation structure is improved.",
        "SPIKE": "Evidence is insufficient for committed implementation planning.",
        "CONFIGURATION_CHANGE": "The approved outcome can be delivered through bounded configuration without new product capability.",
        "DOCUMENTATION_UPDATE": "The approved outcome changes engineering guidance rather than runtime behavior.",
        "MIXED_RECOMMENDATION": "The requirement spans more than one safe implementation strategy and should be separated during Planning Proposal review.",
        "AI_RECOMMENDED": "Available evidence supports bounded planning but requires human confirmation.",
    }[strategy]


def _business_impact(strategy: str, requirement: dict[str, Any]) -> str:
    goals = _strings(requirement.get("businessGoals"))
    return goals[0] if goals else f"{_strategy_title(strategy)} supports the approved requirement outcome."


def _engineering_impact(strategy: str, context: dict[str, Any]) -> str:
    count = len(context.get("repository", {}).get("affectedModules") or [])
    return f"{_strategy_title(strategy)} affects {count} evidence-matched repository module{'s' if count != 1 else ''}."


def _repository_impact(repository: dict[str, Any]) -> str:
    if repository.get("mode") != "CodeIndexed":
        return "Repository impact is provisional because indexed code evidence is unavailable."
    return f"Use {repository.get('reusePercent', 0)}% reusable repository context and limit work to evidence-ranked modules, APIs, services, screens, and tests."


def _ado_impact(actions: list[dict[str, Any]]) -> str:
    return f"{len(actions)} recommended planning action{'s' if len(actions) != 1 else ''}; no Azure DevOps write occurs until Planning Proposal approval."


def _pros(strategy: str) -> list[str]:
    return {
        "NEW_EPIC": ["Clear portfolio ownership", "Independent roadmap visibility"],
        "NEW_INITIATIVE": ["Clear ownership boundary", "Independent roadmap visibility"],
        "NEW_FEATURE": ["Distinct capability ownership", "Measurable feature value"],
        "NEW_STORY": ["Smallest independently valuable change", "Uses existing Feature ownership"],
        "EXTEND_EXISTING_FEATURE": ["Avoids duplicate Features", "Reuses existing ownership"],
        "EXTEND_EXISTING_EPIC": ["Preserves portfolio hierarchy", "Limits new top-level scope"],
        "MODIFY_EXISTING_STORY": ["Minimal backlog change", "Preserves current lineage"],
        "EXTEND_EXISTING_STORY": ["Preserves current Story lineage", "Avoids duplicate user outcomes"],
        "BUG_FIX": ["Focused corrective scope", "Supports regression validation"],
        "ENHANCEMENT": ["Builds on current behavior", "Avoids unnecessary hierarchy"],
        "TECHNICAL_DEBT": ["Improves maintainability", "Keeps product behavior stable"],
        "REFACTOR": ["Preserves behavior", "Improves engineering structure"],
        "REFACTOR_EXISTING_FEATURE": ["Preserves feature behavior", "Improves maintainability"],
        "SPIKE": ["Reduces uncertainty", "Avoids premature commitment"],
        "CONFIGURATION_CHANGE": ["Minimal implementation surface", "Lower deployment risk"],
        "DOCUMENTATION_UPDATE": ["No runtime change", "Fast governance improvement"],
        "MIXED_RECOMMENDATION": ["Separates different work intents", "Makes trade-offs explicit"],
        "AI_RECOMMENDED": ["Keeps human decision open", "Uses available evidence"],
    }[strategy]


def _cons(strategy: str) -> list[str]:
    return {
        "NEW_EPIC": ["Creates broad new hierarchy", "Highest coordination cost"],
        "NEW_INITIATIVE": ["Creates broad new hierarchy", "Higher coordination cost"],
        "NEW_FEATURE": ["May overlap an existing Feature", "Requires new approval boundary"],
        "NEW_STORY": ["Adds backlog scope", "Still requires task decomposition"],
        "EXTEND_EXISTING_FEATURE": ["Can increase Feature scope", "Depends on existing ownership"],
        "EXTEND_EXISTING_EPIC": ["Adds capability under current roadmap", "May affect Epic estimates"],
        "MODIFY_EXISTING_STORY": ["Can invalidate prior review", "Requires revision protection"],
        "EXTEND_EXISTING_STORY": ["Can expand accepted scope", "Requires acceptance-criteria review"],
        "BUG_FIX": ["Does not cover broad enhancement scope", "Requires regression evidence"],
        "ENHANCEMENT": ["Can blur existing scope", "May require Story splitting"],
        "TECHNICAL_DEBT": ["Business value may be indirect", "Competes with product delivery"],
        "REFACTOR": ["Regression risk", "Must preserve behavior"],
        "REFACTOR_EXISTING_FEATURE": ["Feature-wide regression risk", "Business value can be indirect"],
        "SPIKE": ["Does not deliver production behavior", "Requires a later planning decision"],
        "CONFIGURATION_CHANGE": ["May hide deeper design debt", "Environment parity must be verified"],
        "DOCUMENTATION_UPDATE": ["Does not change product behavior", "Can become stale without ownership"],
        "MIXED_RECOMMENDATION": ["Requires decomposition", "Higher review and coordination effort"],
        "AI_RECOMMENDED": ["Lower decision certainty", "Requires stronger human review"],
    }[strategy]


def _canonical_engineering_context(value: dict[str, Any]) -> dict[str, Any]:
    canonical = value.get("engineeringContext")
    if isinstance(canonical, dict):
        return canonical
    if value.get("contextId") or value.get("contextVersion"):
        result = dict(value)
        if "engineeringMemory" not in result and isinstance(result.get("memory"), dict):
            result["engineeringMemory"] = result["memory"]
        similar = result.get("similarWork")
        if isinstance(similar, list):
            result["similarWork"] = {"matches": similar}
        return result
    return {}


def _is_strategy(value: Any) -> bool:
    return _text(value).upper() in {item.value for item in RecommendationStrategy}


def _strategy_option(
    strategy: str,
    confidence: int,
    context: dict[str, Any],
    *,
    description: str,
    selected: bool,
) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "title": _strategy_title(strategy),
        "description": description or _action_reason(strategy),
        "pros": _pros(strategy),
        "cons": _cons(strategy),
        "estimatedEffort": _estimated_effort(context, strategy),
        "risks": _strategy_risks(strategy, context),
        "reuseScore": _reuse_score(context, strategy),
        "confidence": max(0, min(100, int(confidence or 0))),
        "selected": selected,
    }


def _alternative_option(value: RecommendationAlternative) -> dict[str, Any]:
    return {
        "strategy": value.strategy,
        "title": value.title,
        "description": value.description,
        "pros": value.pros,
        "cons": value.cons,
        "estimatedEffort": value.estimatedEffort,
        "risks": value.risks,
        "reuseScore": value.reuseScore,
        "confidence": value.confidence,
        "selected": False,
    }


def _estimated_effort(context: dict[str, Any], strategy: str) -> str:
    complexity = _text((context.get("impact") or {}).get("complexity")).casefold()
    if strategy == "SPIKE":
        return "1-3 discovery days"
    if strategy == "DOCUMENTATION_UPDATE":
        return "1-2 engineering days"
    if strategy == "CONFIGURATION_CHANGE":
        return "1-3 engineering days"
    if complexity == "high":
        return "8-15 engineering days"
    if complexity == "low":
        return "1-3 engineering days"
    return "3-8 engineering days"


def _strategy_risks(strategy: str, context: dict[str, Any]) -> list[str]:
    risks = _strings((context.get("impact") or {}).get("potentialRisks"))
    if strategy in {"MODIFY_EXISTING_STORY", "EXTEND_EXISTING_STORY"}:
        risks.append("The existing work-item scope and acceptance criteria may require revision.")
    if strategy in {"REFACTOR", "REFACTOR_EXISTING_FEATURE"}:
        risks.append("Behavior-preservation and regression evidence are required.")
    if strategy in {"NEW_EPIC", "NEW_INITIATIVE"}:
        risks.append("A new portfolio boundary increases coordination and approval cost.")
    return _unique(risks)[:8]


def _reuse_score(context: dict[str, Any], strategy: str) -> int:
    repository = context.get("repository") or {}
    memory = context.get("memory") or context.get("engineeringMemory") or {}
    similar = list(context.get("similarWork") or [])
    score = (
        int(repository.get("reusePercent") or 0) * 0.55
        + int(memory.get("coverage") or 0) * 0.2
        + max([int(item.get("similarity") or 0) for item in similar] or [0]) * 0.25
    )
    if strategy in {"NEW_EPIC", "NEW_INITIATIVE", "NEW_FEATURE"}:
        score *= 0.75
    return max(0, min(100, round(score)))


def _evidence_item(
    name: Any,
    item_type: str,
    *,
    reason: str,
    impact: str = "Review",
    confidence: int = 0,
    source: str,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": _text(name),
        "type": item_type,
        "reason": reason,
        "impact": impact,
        "confidence": max(0, min(100, int(confidence or 0))),
        "source": source,
        "evidence": _unique(evidence or []),
    }


def _repository_items(
    values: Any,
    item_type: str,
    repository: dict[str, Any],
    reason: str,
) -> list[dict[str, Any]]:
    output = []
    for value in values or []:
        name = value.get("name") or value.get("path") if isinstance(value, dict) else value
        if not _text(name):
            continue
        confidence = value.get("confidence") if isinstance(value, dict) else repository.get("confidence")
        evidence = _strings(value.get("evidence")) if isinstance(value, dict) else []
        output.append(_evidence_item(
            name, item_type, reason=reason, impact="Affected",
            confidence=int(confidence or repository.get("confidence") or 0),
            source="Repository Intelligence", evidence=evidence,
        ))
    return output


def _repository_analysis(context: dict[str, Any]) -> dict[str, Any]:
    repository = context.get("repository") or {}
    repository_name = repository.get("repositoryName")
    repositories = []
    if repository_name or repository.get("repositoryId"):
        repositories.append(_evidence_item(
            repository_name or repository.get("repositoryId"), "Repository",
            reason="Selected by the reviewed Engineering Context.",
            impact="Primary", confidence=int(repository.get("confidence") or 0),
            source="Repository Intelligence",
            evidence=_strings(repository.get("warnings")),
        ))
    screens = repository.get("affectedScreens") or repository.get("screens") or []
    mobile = [
        item for item in screens
        if any(term in _text(item).casefold() for term in ("mobile", "android", "ios", "flutter"))
    ]
    return {
        "repositories": repositories,
        "modules": _repository_items(
            repository.get("affectedModules") or repository.get("modules"), "Module",
            repository, "Module matched the requirement and repository graph.",
        ),
        "apis": _repository_items(
            repository.get("affectedApis") or repository.get("apiEndpoints"), "API",
            repository, "API is present in the selected repository context.",
        ),
        "services": _repository_items(
            repository.get("affectedServices") or repository.get("services"), "Service",
            repository, "Service is present in the selected repository context.",
        ),
        "database": _repository_items(
            repository.get("databaseObjects"), "Database Object", repository,
            "Database object is present in the selected repository context.",
        ),
        "ui": _repository_items(
            screens, "Screen", repository,
            "Screen is present in the selected repository context.",
        ),
        "mobileApps": _repository_items(
            mobile, "Mobile Application", repository,
            "Mobile surface is present in the selected repository context.",
        ),
        "integrations": _repository_items(
            repository.get("integrations"), "Integration", repository,
            "Integration is present in the selected repository context.",
        ),
    }


def _existing_work_detection(context: dict[str, Any]) -> dict[str, Any]:
    similar = list(context.get("similarWork") or [])
    memory = context.get("memory") or context.get("engineeringMemory") or {}
    reuse = context.get("reuse") or {}
    return {
        "alreadyExists": [item for item in similar if int(item.get("similarity") or 0) >= 90],
        "similarStories": [
            item for item in similar
            if _text(item.get("workItemType")).casefold() in {"story", "product backlog item"}
        ],
        "possibleDuplicates": [item for item in similar if int(item.get("similarity") or 0) >= 78],
        "reusableImplementations": list(reuse.get("implementations") or []),
        "mergedPullRequests": list(reuse.get("pullRequests") or []),
        "memoryMatches": list(memory.get("matches") or []),
    }


def _reuse_suggestions(context: dict[str, Any]) -> list[dict[str, Any]]:
    repository = context.get("repository") or {}
    reuse = context.get("reuse") or {}
    suggestions: list[dict[str, Any]] = []
    categories = (
        ("Component", repository.get("reusableComponents") or repository.get("sharedComponents")),
        ("API", repository.get("affectedApis") or repository.get("apiEndpoints")),
        ("Module", repository.get("affectedModules")),
        ("Service", repository.get("affectedServices") or repository.get("services")),
        ("Screen", repository.get("affectedScreens") or repository.get("screens")),
        ("Test", repository.get("reusableTests") or repository.get("tests")),
        ("Implementation", reuse.get("implementations")),
        ("Workflow", reuse.get("patterns")),
    )
    for kind, values in categories:
        for item in values or []:
            name = item.get("name") or item.get("title") or item.get("path") if isinstance(item, dict) else item
            if not _text(name):
                continue
            suggestions.append({
                "type": kind,
                "name": _text(name),
                "reason": f"{kind} appears in the reviewed Engineering Context and may reduce duplicate implementation.",
                "confidence": int((item.get("confidence") if isinstance(item, dict) else None) or repository.get("confidence") or 0),
                "source": "Engineering Context",
                "evidence": _strings(item.get("evidence")) if isinstance(item, dict) else [],
            })
    for item in context.get("similarWork") or []:
        if int(item.get("similarity") or 0) >= 55:
            suggestions.append({
                "type": "Story",
                "name": _text(item.get("title")),
                "reason": _text(item.get("reason")) or "Similar synchronized work may be reused or extended.",
                "confidence": int(item.get("similarity") or 0),
                "source": "Azure DevOps Intelligence",
                "evidence": [_text(item.get("workItemId"))],
            })
    return _unique_dicts(suggestions, ("type", "name"))[:30]


def _dependency_values(values: Any, category: str, source: str) -> list[dict[str, Any]]:
    output = []
    for item in values or []:
        if isinstance(item, dict):
            name = item.get("name") or item.get("title") or item.get("toName") or item.get("to")
            evidence = _strings(item.get("evidence"))
            confidence = int(item.get("confidence") or 70)
        else:
            name, evidence, confidence = item, [], 65
        if _text(name):
            output.append(_evidence_item(
                name, category, reason=f"{category} is present in the reviewed Engineering Context.",
                impact="Dependency", confidence=confidence, source=source, evidence=evidence,
            ))
    return output


def _dependency_analysis(context: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    dependencies = context.get("dependencies") or {}
    requirement = context.get("requirement") or {}
    impact = context.get("impact") or {}
    return {
        "technicalDependencies": _dependency_values(
            list(dependencies.get("moduleDependencies") or [])
            + list(dependencies.get("architectureDependencies") or []),
            "Technical Dependency", "Engineering Graph",
        ),
        "businessDependencies": _dependency_values(
            requirement.get("dependencies") or dependencies.get("storyDependencies") or [],
            "Business Dependency", "Requirement Intelligence",
        ),
        "crossTeamDependencies": _dependency_values(
            dependencies.get("crossTeamDependencies") or [],
            "Cross-team Dependency", "Azure DevOps Intelligence",
        ),
        "apiDependencies": _dependency_values(
            dependencies.get("apiDependencies") or [],
            "API Dependency", "Engineering Graph",
        ),
        "infrastructureDependencies": _dependency_values(
            dependencies.get("infrastructureDependencies") or [],
            "Infrastructure Dependency", "Engineering Context",
        ),
        "repositoryDependencies": _dependency_values(
            dependencies.get("repositoryDependencies") or [],
            "Repository Dependency", "Engineering Graph",
        ),
        "riskDependencies": _dependency_values(
            impact.get("potentialRisks") or [],
            "Risk Dependency", "Impact Analysis",
        ),
    }


def _engineering_impact_summary(context: dict[str, Any]) -> dict[str, Any]:
    impact = context.get("impact") or {}
    repository = context.get("repository") or {}
    risk = _text((context.get("summary") or {}).get("engineeringRisk") or impact.get("risk")) or "Medium"
    module_count = len(repository.get("affectedModules") or [])
    return {
        "complexity": _text(impact.get("complexity") or impact.get("engineeringComplexity")) or "Medium",
        "repositoryImpact": "Unavailable" if repository.get("mode") != "CodeIndexed" else f"{module_count} evidence-matched modules",
        "architectureImpact": _text(impact.get("architectureImpact")) or ("Review required" if module_count else "No architecture impact identified"),
        "riskScore": int(impact.get("riskScore") or {"Low": 25, "Medium": 50, "High": 75, "Critical": 95}.get(risk, 50)),
        "maintenanceImpact": _text(impact.get("maintenanceImpact")) or "Review during Planning Proposal",
        "deploymentImpact": _text(impact.get("deploymentImpact")) or "Not established",
        "testingImpact": _text(impact.get("testingImpact")) or ("Regression review required" if module_count else "Repository evidence unavailable"),
        "regressionRisk": _text(impact.get("regressionRisk")) or risk,
    }


def _recommendation_readiness(context: dict[str, Any]) -> dict[str, Any]:
    requirement = context.get("requirement") or {}
    existing = context.get("readiness") or {}
    functional = len(requirement.get("functionalRequirements") or [])
    acceptance = len(requirement.get("acceptanceCriteria") or [])
    dependencies = _dependency_analysis(context)
    unresolved = sum(len(value) for value in dependencies.values())
    completeness = int(existing.get("requirementCompleteness") or min(100, 35 + functional * 10 + acceptance * 8))
    acceptance_coverage = min(100, round(acceptance / max(1, functional) * 100))
    dependency_resolution = int(existing.get("dependencyResolution") or (70 if unresolved else 90))
    business_clarity = 90 if requirement.get("businessGoals") else 45
    architecture = context.get("architecture") or {}
    architecture_confidence = 85 if architecture.get("modules") or architecture.get("layers") else 45
    overall = round(
        completeness * 0.25 + acceptance_coverage * 0.25
        + dependency_resolution * 0.2 + business_clarity * 0.15
        + architecture_confidence * 0.15
    )
    if overall >= 75:
        status = "Ready"
    elif overall >= 45:
        status = "Needs Clarification"
    else:
        status = "Blocked"
    reasons = []
    if not acceptance:
        reasons.append("Acceptance criteria are missing or not approved.")
    if not requirement.get("businessGoals"):
        reasons.append("Business goal clarification is required.")
    return {
        "requirementCompleteness": completeness,
        "acceptanceCriteriaCoverage": acceptance_coverage,
        "dependencyResolution": dependency_resolution,
        "businessClarity": business_clarity,
        "architectureConfidence": architecture_confidence,
        "overallReadiness": overall,
        "status": status,
        "reasons": reasons,
    }


def _missing_information(context: dict[str, Any]) -> dict[str, list[str]]:
    requirement = context.get("requirement") or {}
    synthesis = context.get("knowledge_synthesis") or {}
    markdown_claims = synthesis.get("repositoryMarkdownClaims") or {}
    missing_acceptance = [] if requirement.get("acceptanceCriteria") else [
        "Define measurable acceptance criteria before Planning Proposal approval."
    ]
    missing_rules = [] if (
        requirement.get("businessRules") or markdown_claims.get("businessRules")
    ) else [
        "No explicit business rules were supplied."
    ]
    missing_constraints = [] if (
        requirement.get("constraints") or markdown_claims.get("constraints")
    ) else [
        "No explicit implementation or operational constraints were supplied."
    ]
    missing_dependencies = [] if (
        requirement.get("dependencies")
        or markdown_claims.get("integrationContracts")
        or markdown_claims.get("architectureDecisions")
    ) else [
        "No explicit business dependencies were supplied."
    ]
    clarifications = _strings(requirement.get("openQuestions"))
    if not requirement.get("businessGoals"):
        clarifications.append("Confirm the measurable business outcome.")
    questions = list(clarifications)
    if missing_acceptance:
        questions.append("Which observable outcomes must be true for Product Owner acceptance?")
    return {
        "clarificationsRequired": _unique(clarifications),
        "missingBusinessRules": missing_rules,
        "missingConstraints": missing_constraints,
        "missingDependencies": missing_dependencies,
        "missingAcceptanceCriteria": missing_acceptance,
        "questionsForProductOwner": _unique(questions),
    }


def _recommendation_explanation(
    strategy: str,
    reasoning: list[str],
    alternatives: list[RecommendationAlternative],
    reasoning_result: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    evidence = []
    for reason in reasoning_result.get("evidence") or []:
        if isinstance(reason, dict):
            evidence.append(_text(reason.get("referenceId") or reason.get("reason")))
        else:
            evidence.append(_text(reason))
    if not evidence:
        evidence = [
            _text(context.get("contextId")),
            *(_strings((context.get("repository") or {}).get("affectedModules"))[:5]),
        ]
    return {
        "whyThisApproach": reasoning[0] if reasoning else _action_reason(strategy),
        "whyNotAlternatives": [
            f"{item.title}: {item.rejectedReason}" for item in alternatives
        ],
        "tradeOffs": _unique(
            _strings(reasoning_result.get("tradeOffs")) + _cons(strategy)
        ),
        "evidenceUsed": _unique(evidence),
        "confidence": reasoning_result.get("confidence") or {},
        "potentialFutureImpact": (
            "Planning Proposal may refine estimates and hierarchy, but it must preserve "
            "this approved implementation boundary and context lineage."
        ),
    }


def _bounded_reasoning_result(value: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "recommendation", "reasoning", "alternatives", "evidence", "risks",
        "tradeOffs", "impact", "confidence", "reasoningMode", "promptVersion",
        "provider", "model", "telemetry", "warnings",
    )
    return {key: value.get(key) for key in keys if key in value}


def _unique_dicts(values: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for value in values:
        identity = tuple(_text(value.get(key)).casefold() for key in keys)
        if not any(identity) or identity in seen:
            continue
        seen.add(identity)
        output.append(value)
    return output


def _operation(action: str, artifact_type: str, title: str, reason: str, confidence: int) -> dict[str, Any]:
    return {
        "operationId": "operation-" + _digest([action, artifact_type, title]),
        "action": action,
        "artifactType": artifact_type,
        "title": title,
        "reason": reason,
        "confidence": confidence,
    }


def _short_title(value: str) -> str:
    words = value.replace(".", " ").split()
    return " ".join(word if word.isupper() else word.capitalize() for word in words[:9]) or "Review Requirement Outcome"


def _for_context(values: dict[str, Any], context_id: str) -> dict[str, Any] | None:
    return next((item for item in values.values() if isinstance(item, dict) and item.get("contextId") == context_id), None)


def _required(request: dict[str, Any], key: str) -> str:
    value = _text(request.get(key))
    if not value:
        raise ValueError(f"{key} is required.")
    return value


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item.get("text") if isinstance(item, dict) else item) for item in value if _text(item.get("text") if isinstance(item, dict) else item)]
    return [_text(value)] if _text(value) else []


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
