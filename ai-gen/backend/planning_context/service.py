"""Persisted engineering-landscape context built before Planning Intelligence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.platform.shared import JsonMapStore
from backend.engineering_intelligence import EngineeringIntelligenceService
from backend.requirement_analysis.summary import build_requirement_summary

from .models import (
    PlanningClassification,
    PlanningContext,
    PlanningImpact,
    PlanningMemory,
    PlanningRecommendation,
    PlanningRepository,
    PlanningSimilarity,
    PlanningSummary,
)


CLASSIFICATIONS = {
    "NEW_INITIATIVE", "NEW_FEATURE", "EXTEND_FEATURE", "MODIFY_EXISTING",
    "BUG", "ENHANCEMENT", "AI_RECOMMENDED",
}


class PlanningContextService:
    """Builds, stores, refreshes, classifies, and reviews Planning Context."""

    def __init__(
        self,
        store: JsonMapStore,
        *,
        requirement_ingestion: Any,
        requirement_analysis: Any,
        intelligence_engine: Any,
        repository_intelligence: Any | None = None,
        pull_request_provider: Any | None = None,
        engineering_intelligence: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.requirement_ingestion = requirement_ingestion
        self.requirement_analysis = requirement_analysis
        self.intelligence_engine = intelligence_engine
        self.repository_intelligence = repository_intelligence
        pull_requests = pull_request_provider or (lambda _project_id: [])
        self.engineering_intelligence = engineering_intelligence or EngineeringIntelligenceService(
            repository_intelligence=repository_intelligence,
            planning_engine=intelligence_engine,
            pull_request_provider=pull_requests,
        )
        self.platform = platform

    def build(self, request: dict[str, Any]) -> dict[str, Any]:
        requirement_id = _required(request, "requirementId")
        summary = self._approved_summary(requirement_id)
        builder = getattr(self.engineering_intelligence, "build_planning_context", None)
        if not callable(builder):
            builder = self.engineering_intelligence.generate_planning_context
        engineering_result = builder(
            summary,
            correlation_id=_text(summary.get("correlationId") or request.get("correlationId")),
        )
        raw = engineering_result["rawContext"]
        analysis = engineering_result["analysis"]
        recommended = engineering_result["planningRecommendationInput"]
        record = self._assemble(summary, raw, analysis, recommended, request)
        record["engineeringContext"] = engineering_result["engineeringContext"]
        record["architecture"] = engineering_result["engineeringContext"].get("architecture") or {}
        record["dependencies"] = engineering_result["engineeringContext"].get("dependencies") or {}
        record["reuse"] = engineering_result["engineeringContext"].get("reuse") or {}
        record["engineeringDiscovery"] = {
            "repositoryMarkdown": engineering_result["engineeringContext"].get(
                "repository_markdown_context"
            ) or {},
            "projectIntelligence": engineering_result["engineeringContext"].get(
                "project_intelligence_context"
            ) or {},
            "knowledgeSynthesis": engineering_result["engineeringContext"].get(
                "knowledge_synthesis"
            ) or {},
            "sourceVersions": engineering_result["engineeringContext"].get(
                "sourceVersions"
            ) or {},
        }
        values = self.store.read()
        existing = values.get(record["contextId"])
        if isinstance(existing, dict) and request.get("force") is not True:
            return existing
        values[record["contextId"]] = record
        self.store.write(values)
        self._publish("PlanningContextBuilt", record)
        return record

    def get(self, context_id: str) -> dict[str, Any]:
        record = self.store.read().get(context_id)
        if not isinstance(record, dict):
            raise LookupError("Planning Context was not found.")
        return record

    def refresh(self, request: dict[str, Any]) -> dict[str, Any]:
        context_id = _text(request.get("contextId"))
        if context_id:
            current = self.get(context_id)
            requirement_id = current["requirementId"]
        else:
            requirement_id = _required(request, "requirementId")
        return self.build({**request, "requirementId": requirement_id, "force": True})

    def classify(self, request: dict[str, Any]) -> dict[str, Any]:
        context_id = _required(request, "contextId")
        value = _required(request, "classification").upper()
        if value not in CLASSIFICATIONS:
            raise ValueError(f"classification must be one of: {', '.join(sorted(CLASSIFICATIONS))}.")
        actor = _required(request, "actor")
        values = self.store.read()
        record = self.get(context_id)
        record["classification"] = {
            "value": value,
            "confidence": 100,
            "reason": _text(request.get("reason")) or "Manually selected during Planning Context review.",
            "source": "ManualOverride",
            "overriddenBy": actor,
        }
        record["recommendation"]["planningMode"] = value
        record["summary"]["planningMode"] = value
        record["status"] = "NeedsReview"
        record["reviewStatus"] = "Pending"
        values[context_id] = record
        self.store.write(values)
        self._publish("PlanningContextClassificationChanged", record)
        return record

    def analyze(self, request: dict[str, Any]) -> dict[str, Any]:
        context_id = _required(request, "contextId")
        decision = _text(request.get("decision")) or "Review"
        record = self.get(context_id)
        if decision.casefold() in {"accept", "approve", "continue"}:
            if record.get("readiness", {}).get("status") == "Blocked":
                raise ValueError("Blocked Planning Context cannot be approved.")
            record["reviewStatus"] = "Reviewed"
            record["status"] = "Completed"
            record["reviewedBy"] = _required(request, "actor")
            record["reviewedAt"] = _now()
            event = "PlanningContextReviewed"
        elif decision.casefold() == "savedraft":
            record["reviewStatus"] = "Draft"
            record["status"] = "Draft"
            event = "PlanningContextDraftSaved"
        else:
            record["reviewStatus"] = "Pending"
            event = "PlanningContextAnalyzed"
        values = self.store.read()
        values[context_id] = record
        self.store.write(values)
        self._publish(event, record)
        return record

    def require_reviewed(self, context_id: str, requirement_id: str) -> dict[str, Any]:
        if not context_id:
            raise ValueError("Planning Context must be completed before Planning begins.")
        record = self.get(context_id)
        if record.get("requirementId") != requirement_id:
            raise ValueError("Planning Context does not belong to this Requirement Summary.")
        summary = self._approved_summary(requirement_id)
        if (
            record.get("requirementContextVersion") != summary.get("contextVersion")
            or record.get("analysisId") != summary.get("analysisId")
        ):
            raise ValueError("Planning Context is stale. Refresh and review it before Planning.")
        if record.get("status") != "Completed" or record.get("reviewStatus") != "Reviewed":
            raise ValueError("Review the Planning Context before Planning begins.")
        return record

    def _assemble(
        self,
        summary: dict[str, Any],
        raw: dict[str, Any],
        analysis: dict[str, Any],
        recommended: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        repository = raw.get("repository") or {}
        graph = repository.get("graph") or {}
        nodes = list(graph.get("nodes") or [])
        affected = self._affected_repository_items(summary, repository, nodes)
        memory_matches = list(raw.get("engineeringMemory", {}).get("matches") or [])
        memory = PlanningMemory(
            matches=memory_matches,
            previousStories=[item for item in memory_matches if _text(item.get("artifactType")).casefold() == "story"],
            previousPullRequests=[item for item in memory_matches if "pull" in _text(item.get("artifactType")).casefold()],
            previousBugs=[item for item in memory_matches if _text(item.get("artifactType")).casefold() == "bug"],
            architectureDecisions=[item for item in memory_matches if "architecture" in _text(item.get("category")).casefold()],
            reusableComponents=affected["components"],
            reusableTests=affected["tests"],
            lessonsLearned=[item["title"] for item in memory_matches if "lesson" in _text(item.get("category")).casefold()],
            coverage=min(100, len(memory_matches) * 12),
        )
        similarities = [
            PlanningSimilarity(
                workItemId=_text(item.get("workItem", {}).get("id")),
                workItemType=_text(item.get("workItem", {}).get("type")),
                title=_text(item.get("workItem", {}).get("title")),
                similarity=round(float(item.get("confidence") or 0) * 100),
                confidence=round(float(item.get("confidence") or 0) * 100),
                reason=_text(item.get("reason")),
                suggestedAction=_similar_action(item),
                state=_text(item.get("workItem", {}).get("state")),
            )
            for item in list(analysis.get("similarWork") or [])
        ]
        mode = _classification(recommended.get("mode"), summary)
        classification = PlanningClassification(
            value=mode,
            confidence=int(recommended.get("confidence") or 0),
            reason=" ".join(_strings(recommended.get("reason"))),
        )
        risks = _strings(summary.get("risks"))
        complexity = "High" if len(affected["modules"]) > 4 or len(similarities) > 8 else "Medium" if affected["modules"] or similarities else "Low"
        impact = PlanningImpact(
            affectedFeatures=[item.title for item in similarities if item.workItemType == "Feature"][:8],
            affectedStories=[item.title for item in similarities if item.workItemType == "Story"][:12],
            affectedApis=affected["apis"],
            affectedModules=affected["modules"],
            potentialRisks=risks or ["Validate repository and integration impact during Planning."],
            potentialBreakingChanges=["Existing API contract may require compatibility validation."] if affected["apis"] else [],
            sprintImpact="Review current sprint capacity." if raw.get("azureDevOps", {}).get("currentIterations") else "No current sprint synchronized.",
            engineeringEffort="Estimate after Planning Recommendation",
            complexity=complexity,
        )
        repo_confidence = int(analysis.get("repositoryMatch", {}).get("confidence") or 0)
        planning_repository = PlanningRepository(
            repositoryId=_text(repository.get("repositoryId")),
            repositoryName=_text(repository.get("repositoryName")),
            mode=_text(repository.get("mode")) or "Unavailable",
            branch=_text(repository.get("branch")),
            snapshotId=_text(repository.get("snapshotId")),
            snapshotVersion=_text(repository.get("repositorySnapshotVersion")),
            confidence=repo_confidence,
            affectedModules=affected["modules"],
            affectedServices=affected["services"],
            affectedApis=affected["apis"],
            affectedScreens=affected["screens"],
            reusableComponents=affected["components"],
            reusableTests=affected["tests"],
            reusePercent=min(95, len(affected["components"]) * 12 + len(affected["apis"]) * 8 + len(affected["tests"]) * 5),
            reason=_text(analysis.get("repositoryMatch", {}).get("reason")),
            warnings=_strings(repository.get("warnings")),
        )
        readiness = _readiness(summary, planning_repository, memory, similarities)
        strategy = _text(recommended.get("recommendedStrategy", {}).get("description"))
        recommendation = PlanningRecommendation(
            planningMode=mode,
            confidence=int(recommended.get("confidence") or 0),
            strategy=strategy,
            create=[item.title for item in similarities if item.suggestedAction == "Create New"],
            reuse=[item.title for item in similarities if item.suggestedAction == "Reuse"],
            modify=[item.title for item in similarities if item.suggestedAction == "Modify"],
            doNotCreate=[item.title for item in similarities if item.suggestedAction in {"Reuse", "Modify"}],
            reasons=_strings(recommended.get("reason")),
        )
        context_id = _text(raw.get("contextId"))
        context = PlanningContext(
            contextId=context_id,
            contextVersion=_text(raw.get("contextVersion")),
            requirementId=_text(summary.get("requirementId")),
            requirementContextVersion=_text(summary.get("contextVersion")),
            analysisId=_text(summary.get("analysisId")),
            projectId=_text(summary.get("projectId")),
            requirement={
                "title": _text(summary.get("title")),
                "planningRequirement": _text(summary.get("planningRequirement")),
                "businessGoals": _strings(summary.get("businessGoals")),
                "functionalRequirements": _strings(summary.get("functionalRequirements")),
                "nonFunctionalRequirements": _strings(summary.get("nonFunctionalRequirements")),
                "acceptanceCriteria": _strings(summary.get("acceptanceCriteria")),
                "acceptanceCriteriaRecords": [
                    dict(item) for item in summary.get("acceptanceCriteriaRecords") or []
                    if isinstance(item, dict)
                ],
                "acceptanceCriteriaState": dict(summary.get("acceptanceCriteriaState") or {}),
                "acceptanceCoverage": dict(summary.get("acceptanceCoverage") or {}),
                "acceptanceEvidence": [
                    dict(item) for item in summary.get("acceptanceEvidence") or []
                    if isinstance(item, dict)
                ],
                "fieldOrigins": dict(summary.get("fieldOrigins") or {}),
                "businessRules": _strings(summary.get("businessRules")),
                "dependencies": _strings(summary.get("dependencies")),
                "risks": _strings(summary.get("risks")),
                "constraints": _strings(summary.get("constraints")),
                "actors": _strings(summary.get("actors")),
                "assumptions": _strings(summary.get("assumptions")),
                "openQuestions": _strings(summary.get("openQuestions")),
                "analysisDocument": dict(summary.get("canonicalRequirementAnalysis") or {}),
            },
            status="Blocked" if readiness["status"] == "Blocked" else "NeedsReview",
            reviewStatus="Pending",
            azureDevOps=_azure_devops_summary(
                raw.get("azureDevOps") or {},
                _text(summary.get("projectId")),
                list(raw.get("azureDevOps", {}).get("openPullRequests") or []),
            ),
            repository=planning_repository,
            memory=memory,
            similarWork=similarities,
            classification=classification,
            impact=impact,
            recommendation=recommendation,
            readiness=readiness,
            summary=PlanningSummary(
                currentProject=_text(summary.get("projectName") or summary.get("projectId")),
                repository=planning_repository.repositoryName or "Continue without Repository",
                planningMode=mode,
                recommendedStrategy=strategy,
                affectedFeatures=len(impact.affectedFeatures),
                affectedStories=len(impact.affectedStories),
                engineeringRisk="High" if impact.potentialBreakingChanges else "Medium" if risks else "Low",
                estimatedComplexity=complexity,
                planningConfidence=int(recommended.get("confidence") or 0),
            ),
            correlationId=_text(summary.get("correlationId") or request.get("correlationId")),
            generatedAt=_now(),
        )
        return context.to_dict()

    def _approved_summary(self, requirement_id: str) -> dict[str, Any]:
        requirement = self.requirement_ingestion.get(requirement_id)
        if not requirement:
            raise LookupError("Requirement Context was not found.")
        analysis = self.requirement_analysis.assert_approved(requirement_id)
        return build_requirement_summary(requirement, analysis)

    @staticmethod
    def _affected_repository_items(summary: dict[str, Any], repository: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
        text = " ".join([
            _text(summary.get("title")), _text(summary.get("planningRequirement")),
            *_strings(summary.get("functionalRequirements")), *_strings(summary.get("acceptanceCriteria")),
        ])
        tokens = _tokens(text)
        buckets = {"modules": [], "services": [], "apis": [], "screens": [], "components": [], "tests": []}
        for module in _strings(repository.get("modules")):
            if _tokens(module) & tokens:
                buckets["modules"].append(module)
        mapping = {
            "module": "modules", "service": "services", "api": "apis", "controller": "apis",
            "screen": "screens", "ui": "screens", "viewmodel": "components", "dto": "components",
            "file": "components", "test": "tests",
        }
        for node in nodes:
            name = _text(node.get("name"))
            bucket = mapping.get(_text(node.get("nodeType") or node.get("type")).casefold())
            if bucket and name and (_tokens(name) & tokens):
                buckets[bucket].append(name)
        return {key: _unique(values)[:12] for key, values in buckets.items()}

    def _publish(self, event_type: str, record: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "PlanningContextEngine",
            "projectId": record.get("projectId"),
            "correlationId": record.get("correlationId"),
            "payload": {
                "contextId": record.get("contextId"),
                "requirementId": record.get("requirementId"),
                "status": record.get("status"),
            },
        })


def _azure_devops_summary(value: dict[str, Any], project_id: str, pull_requests: list[dict[str, Any]]) -> dict[str, Any]:
    items = list(value.get("workItems") or [])
    iterations = list(value.get("currentIterations") or [])
    current = next((item for item in iterations if _text(item.get("timeFrame")).casefold() == "current"), iterations[0] if iterations else {})
    return {
        "source": value.get("source"),
        "project": project_id,
        "areaPaths": _unique([_text(item.get("areaPath")) for item in items]),
        "iterations": iterations,
        "currentSprint": current,
        "counts": value.get("counts") or {},
        "workItems": items,
        "hierarchy": value.get("existingHierarchy") or [],
        "tags": _unique([tag for item in items for tag in _strings(item.get("tags"))]),
        "assignedUsers": _unique([_text(item.get("assignedTo")) for item in items]),
        "storyPoints": sum(float(item.get("storyPoints") or 0) for item in items),
        "openPullRequests": [
            item for item in pull_requests
            if _text(item.get("status") or item.get("state")).casefold() not in {"completed", "abandoned", "merged", "closed"}
        ],
        "currentDevelopment": [
            item for item in items
            if _text(item.get("state")).casefold() in {"active", "in progress", "committed", "doing"}
        ],
    }


def _readiness(summary: dict[str, Any], repository: PlanningRepository, memory: PlanningMemory, similar: list[PlanningSimilarity]) -> dict[str, Any]:
    requirement_score = int(summary.get("qualityScore") or 0)
    blockers = _strings(summary.get("planningReadiness", {}).get("blockers"))
    warnings = _strings(summary.get("planningReadiness", {}).get("warnings")) + repository.warnings
    if blockers:
        status = "Blocked"
    elif similar and similar[0].similarity >= 78:
        status = "NeedsUserDecision"
        warnings.append("A close existing work item requires a Reuse, Modify, or Create New decision.")
    elif warnings or repository.mode == "Unavailable":
        status = "ReadyWithRecommendations"
    else:
        status = "Ready"
    score = round(requirement_score * 0.35 + repository.confidence * 0.3 + memory.coverage * 0.15 + (85 if similar else 60) * 0.2)
    return {
        "status": status,
        "score": score,
        "planningContextScore": score,
        "repositoryCoverage": repository.confidence,
        "memoryCoverage": memory.coverage,
        "requirementCompleteness": requirement_score,
        "existingWorkMatch": similar[0].similarity if similar else 0,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
    }


def _similar_action(item: dict[str, Any]) -> str:
    score = float(item.get("confidence") or 0)
    if score >= 0.78:
        return "Modify"
    if score >= 0.55:
        return "Reuse"
    return "Create New"


def _classification(value: Any, summary: dict[str, Any]) -> str:
    normalized = _text(value).upper()
    if normalized == "BUG_OR_ENHANCEMENT":
        requirement = " ".join([_text(summary.get("title")), _text(summary.get("planningRequirement"))]).casefold()
        return "BUG" if any(term in requirement for term in ("bug", "fix", "defect", "error", "issue")) else "ENHANCEMENT"
    return normalized if normalized in CLASSIFICATIONS else "AI_RECOMMENDED"


def _required(request: dict[str, Any], key: str) -> str:
    value = _text(request.get(key))
    if not value:
        raise ValueError(f"{key} is required.")
    return value


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item.get("text") if isinstance(item, dict) else item) for item in value if _text(item.get("text") if isinstance(item, dict) else item)]
    return [_text(value)] if _text(value) else []


def _tokens(value: Any) -> set[str]:
    ignored = {"and", "the", "for", "with", "from", "that", "this", "into", "user", "users"}
    return {token for token in re.findall(r"[a-z0-9]+", _text(value).casefold()) if len(token) > 2 and token not in ignored}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
