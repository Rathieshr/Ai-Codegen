"""Deterministic Planning Recommendation Engine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.platform.shared import JsonMapStore

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

    def __init__(self, store: JsonMapStore, *, planning_context_service: Any, platform: Any | None = None) -> None:
        self.store = store
        self.planning_context_service = planning_context_service
        self.platform = platform

    def build(self, request: dict[str, Any]) -> dict[str, Any]:
        context_id = _required(request, "contextId")
        context = self.planning_context_service.get(context_id)
        context = self.planning_context_service.require_reviewed(context_id, _text(context.get("requirementId")))
        values = self.store.read()
        existing = _for_context(values, context_id)
        if existing and request.get("force") is not True:
            return existing
        version = int((existing or {}).get("version") or 0) + 1
        strategy, scores = _select_strategy(context)
        record = self._assemble(context, strategy, scores, version, existing)
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
        record["history"] = list(record.get("history") or []) + [{
            "action": "Approved", "actor": actor, "at": record["approvedAt"],
            "strategy": record["strategy"], "comments": _text(request.get("comments")),
        }]
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
        scores = {item.value: 20 for item in RecommendationStrategy}
        scores[strategy] = 100
        record = self._assemble(context, strategy, scores, int(current.get("version") or 1) + 1, current)
        record["overrideReason"] = reason
        record["history"] = list(current.get("history") or []) + [{
            "action": "StrategyOverridden", "actor": actor, "at": _now(),
            "from": current.get("strategy"), "to": strategy, "reason": reason,
        }]
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

    def to_engine_recommendation(self, record: dict[str, Any]) -> dict[str, Any]:
        mode_map = {
            "NEW_INITIATIVE": "NEW_INITIATIVE",
            "NEW_FEATURE": "NEW_FEATURE",
            "EXTEND_EXISTING_FEATURE": "EXTEND_FEATURE",
            "EXTEND_EXISTING_EPIC": "NEW_FEATURE",
            "MODIFY_EXISTING_STORY": "MODIFY_EXISTING",
            "BUG_FIX": "BUG_OR_ENHANCEMENT",
            "ENHANCEMENT": "BUG_OR_ENHANCEMENT",
            "TECHNICAL_DEBT": "MODIFY_EXISTING",
            "REFACTOR": "MODIFY_EXISTING",
            "SPIKE": "AI_RECOMMENDED",
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

    def _assemble(
        self,
        context: dict[str, Any],
        strategy: str,
        scores: dict[str, int],
        version: int,
        existing: dict[str, Any] | None,
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
        alternatives = _alternatives(strategy, scores)
        risks = _unique(
            list(impact_context.get("potentialRisks") or [])
            + list(impact_context.get("potentialBreakingChanges") or [])
            + (["Open pull requests overlap the current engineering landscape. Review planned changes against active development."] if related_pull_requests else [])
        )
        reasoning = _reasoning(strategy, context, alternatives)
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
        scores["REFACTOR"] = 94
    if any(term in text for term in ("spike", "investigate", "proof of concept", "prototype", "feasibility")):
        scores["SPIKE"] = 93
    if best_score >= 78 and best_type == "Story":
        scores["MODIFY_EXISTING_STORY"] = max(scores["MODIFY_EXISTING_STORY"], 92)
    if best_score >= 55 and best_type == "Feature":
        scores["EXTEND_EXISTING_FEATURE"] = max(scores["EXTEND_EXISTING_FEATURE"], 90)
    if best_score >= 55 and best_type == "Epic":
        scores["EXTEND_EXISTING_EPIC"] = max(scores["EXTEND_EXISTING_EPIC"], 88)
    strategy = max(scores, key=scores.get)
    return strategy, scores


def _actions(strategy: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    similar_work = list(context.get("similarWork") or [])
    if similar_work and int(similar_work[0].get("similarity") or 0) >= 95 and _text(similar_work[0].get("state")).casefold() in {"done", "closed", "completed"}:
        return [{"action": "Do Nothing", "confidence": 82, "reason": "A completed work item already satisfies nearly all of the approved requirement."}]
    primary = {
        "NEW_INITIATIVE": "Create New Epic",
        "NEW_FEATURE": "Create New Feature",
        "EXTEND_EXISTING_FEATURE": "Create Stories",
        "EXTEND_EXISTING_EPIC": "Create New Feature",
        "MODIFY_EXISTING_STORY": "Modify Existing Story",
        "BUG_FIX": "Create Bug",
        "ENHANCEMENT": "Create Stories",
        "TECHNICAL_DEBT": "Create Tasks",
        "REFACTOR": "Create Tasks",
        "SPIKE": "Create Spike",
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


def _alternatives(selected: str, scores: dict[str, int]) -> list[RecommendationAlternative]:
    alternatives = []
    for strategy, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        if strategy == selected:
            continue
        alternatives.append(RecommendationAlternative(
            strategy=strategy,
            confidence=max(12, min(90, score)),
            title=_strategy_title(strategy),
            pros=_pros(strategy),
            cons=_cons(strategy),
            rejectedReason=f"{_strategy_title(selected)} better matches current backlog similarity, repository evidence, and requirement classification.",
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
    if strategy in {"MODIFY_EXISTING_STORY", "TECHNICAL_DEBT", "REFACTOR"}:
        return ["Modify", "Keep", "Split"]
    if strategy in {"EXTEND_EXISTING_FEATURE", "EXTEND_EXISTING_EPIC"}:
        return ["Keep", "Create", "Link"]
    return ["Create", "Link", "Keep"]


def _action_reason(strategy: str) -> str:
    return {
        "NEW_INITIATIVE": "No existing Epic provides a sufficiently safe parent boundary.",
        "NEW_FEATURE": "The requirement belongs in the current product but needs a distinct capability.",
        "EXTEND_EXISTING_FEATURE": "A synchronized Feature already owns this capability.",
        "EXTEND_EXISTING_EPIC": "A synchronized Epic is the correct parent for a new capability.",
        "MODIFY_EXISTING_STORY": "An existing Story already represents most of the requested behavior.",
        "BUG_FIX": "The requirement describes incorrect existing behavior.",
        "ENHANCEMENT": "The requirement expands an existing user outcome.",
        "TECHNICAL_DEBT": "The work primarily improves maintainability rather than product scope.",
        "REFACTOR": "The implementation should preserve behavior while changing structure.",
        "SPIKE": "Evidence is insufficient for committed implementation planning.",
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
        "NEW_INITIATIVE": ["Clear ownership boundary", "Independent roadmap visibility"],
        "NEW_FEATURE": ["Distinct capability ownership", "Measurable feature value"],
        "EXTEND_EXISTING_FEATURE": ["Avoids duplicate Features", "Reuses existing ownership"],
        "EXTEND_EXISTING_EPIC": ["Preserves portfolio hierarchy", "Limits new top-level scope"],
        "MODIFY_EXISTING_STORY": ["Minimal backlog change", "Preserves current lineage"],
        "BUG_FIX": ["Focused corrective scope", "Supports regression validation"],
        "ENHANCEMENT": ["Builds on current behavior", "Avoids unnecessary hierarchy"],
        "TECHNICAL_DEBT": ["Improves maintainability", "Keeps product behavior stable"],
        "REFACTOR": ["Preserves behavior", "Improves engineering structure"],
        "SPIKE": ["Reduces uncertainty", "Avoids premature commitment"],
        "AI_RECOMMENDED": ["Keeps human decision open", "Uses available evidence"],
    }[strategy]


def _cons(strategy: str) -> list[str]:
    return {
        "NEW_INITIATIVE": ["Creates broad new hierarchy", "Higher coordination cost"],
        "NEW_FEATURE": ["May overlap an existing Feature", "Requires new approval boundary"],
        "EXTEND_EXISTING_FEATURE": ["Can increase Feature scope", "Depends on existing ownership"],
        "EXTEND_EXISTING_EPIC": ["Adds capability under current roadmap", "May affect Epic estimates"],
        "MODIFY_EXISTING_STORY": ["Can invalidate prior review", "Requires revision protection"],
        "BUG_FIX": ["Does not cover broad enhancement scope", "Requires regression evidence"],
        "ENHANCEMENT": ["Can blur existing scope", "May require Story splitting"],
        "TECHNICAL_DEBT": ["Business value may be indirect", "Competes with product delivery"],
        "REFACTOR": ["Regression risk", "Must preserve behavior"],
        "SPIKE": ["Does not deliver production behavior", "Requires a later planning decision"],
        "AI_RECOMMENDED": ["Lower decision certainty", "Requires stronger human review"],
    }[strategy]


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
