"""Read-only work-item analysis over synchronized ADO and orchestrated HEI context."""

from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from typing import Any, Callable
from uuid import uuid4

from backend.context_orchestration import ContextRequest
from backend.intelligence.planning import PlanningEngine
from backend.platform_sdk import as_azure_devops_sdk

from .models import RecommendationStatus, WorkItemRecommendation, now_iso
from .repository import WorkItemRecommendationRepository


AMBIGUOUS = {"appropriate", "as needed", "etc", "fast", "easy", "some", "tbd", "user-friendly", "various"}
FIBONACCI = (1, 2, 3, 5, 8, 13)


class WorkItemNotFoundError(LookupError):
    pass


class RecommendationNotFoundError(LookupError):
    pass


class StaleRecommendationError(RuntimeError):
    pass


class AdoWorkItemIntelligenceService:
    def __init__(self, *, azure_devops: Any, context_orchestrator: Any, repository: WorkItemRecommendationRepository, planning_engine: PlanningEngine | None = None, profile_provider: Callable[[], dict[str, Any]] | None = None, platform: Any | None = None) -> None:
        self.ado_sdk = as_azure_devops_sdk(azure_devops)
        self.context_orchestrator = context_orchestrator
        self.repository = repository
        self.planning_engine = planning_engine or PlanningEngine()
        self.profile_provider = profile_provider or (lambda: {})
        self.platform = platform
        self.estimation: Any | None = None
        self.pull_requests: Any | None = None
        self.sprints: Any | None = None

    def analyze(self, work_item_id: str, request: dict[str, Any] | None = None, *, correlation_id: str = "") -> dict[str, Any]:
        request = request or {}
        work_item, project_id = self._resolve_work_item(work_item_id, request)
        revision = int(work_item.get("revision") or request.get("workItemRevision") or 0)
        correlation_id = correlation_id or f"corr-{uuid4().hex[:16]}"
        self.repository.mark_stale(str(work_item_id), revision, include_same_revision=bool(request.get("regenerate")))
        profile = self.profile_provider() or {}
        knowledge = request.get("knowledgeRegistry") if isinstance(request.get("knowledgeRegistry"), dict) else profile.get("knowledge_registry", {})
        repository_id = str(request.get("repositoryId") or _repository_id(profile, self.ado_sdk.cache_snapshot(project_id)))
        context = self.context_orchestrator.orchestrate(ContextRequest(
            request_id=f"ado-wi-{work_item_id}-{uuid4().hex[:10]}", correlation_id=correlation_id,
            purpose="Planning", project_id=project_id or "manual", repository_id=repository_id,
            artifact=_context_artifact(work_item, knowledge, profile),
            options={"includePlanningLineage": True, "includeRepository": True, "includeKnowledge": True, "includeMemory": True, "maxTokens": int(request.get("tokenBudget") or 1200), "minimumConfidence": 0.35},
        ))
        capsule = _capsule_inputs(context)
        existing = self._other_work_items(project_id, str(work_item_id))
        planning = self.planning_engine.build_planning_context(
            _planning_work_item(work_item), None,
            {"knowledgeRegistry": capsule["knowledgeRegistry"], "repositorySnapshot": capsule["repositorySnapshot"], "existingChildren": existing, "objective": "Analyze requirement quality and recommend controlled decomposition."},
        )
        analysis = self._build_analysis(work_item, project_id, planning, context, existing, correlation_id)
        recommendations = self._recommendations(analysis, work_item)
        for recommendation in recommendations:
            self.repository.save(recommendation)
        analysis["recommendations"] = [item.to_dict() for item in recommendations]
        self.repository.save_analysis(analysis)
        self._event("AdoWorkItemAnalyzed", analysis, correlation_id)
        return analysis

    def list_recommendations(self, work_item_id: str, project_id: str = "") -> dict[str, Any]:
        current = self.ado_sdk.find_cached("workItems", str(work_item_id), project_id)
        if current:
            self.repository.mark_stale(str(work_item_id), int(current[1].get("revision") or 0))
        items = [item.to_dict() for item in self.repository.list(str(work_item_id))]
        return {"workItemId": str(work_item_id), "recommendations": items, "count": len(items)}

    def approve(self, recommendation_id: str, actor: str) -> dict[str, Any]:
        item = self._active_recommendation(recommendation_id)
        item.status = RecommendationStatus.APPROVED
        item.approved_by = actor or "current-user"
        item.approved_at = now_iso()
        result = self.repository.save(item)
        self._event("AdoRecommendationApproved", result, "")
        return result

    def reject(self, recommendation_id: str, actor: str) -> dict[str, Any]:
        item = self._active_recommendation(recommendation_id)
        item.status = RecommendationStatus.REJECTED
        item.rejected_by = actor or "current-user"
        item.rejected_at = now_iso()
        result = self.repository.save(item)
        self._event("AdoRecommendationRejected", result, "")
        return result

    def regenerate(self, recommendation_id: str, request: dict[str, Any] | None = None, *, correlation_id: str = "") -> dict[str, Any]:
        item = self.repository.get(recommendation_id)
        if not item:
            raise RecommendationNotFoundError(recommendation_id)
        payload = dict(request or {})
        payload.update({"projectId": payload.get("projectId") or item.project_id, "regenerate": True})
        return self.analyze(item.work_item_id, payload, correlation_id=correlation_id)

    def _resolve_work_item(self, work_item_id: str, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        project_id = str(request.get("projectId") or "")
        cached = self.ado_sdk.find_cached("workItems", str(work_item_id), project_id)
        if cached:
            return dict(cached[1]), cached[0]
        manual = request.get("manualRequirement") or request.get("importedRequirement")
        if not isinstance(manual, dict):
            manual = request
        if manual.get("title") or manual.get("description"):
            return {
                "workItemId": str(work_item_id), "workItemType": manual.get("workItemType") or "Manual Requirement",
                "title": manual.get("title") or "Untitled requirement", "description": manual.get("description") or "",
                "acceptanceCriteria": manual.get("acceptanceCriteria") or [], "revision": int(manual.get("workItemRevision") or 0),
            }, project_id or "manual"
        raise WorkItemNotFoundError(str(work_item_id))

    def _other_work_items(self, project_id: str, work_item_id: str) -> list[dict[str, Any]]:
        return [dict(item) for key, item in self.ado_sdk.cached_collection(project_id, "workItems").items() if str(key) != work_item_id]

    def _build_analysis(self, item: dict[str, Any], project_id: str, planning: dict[str, Any], context: dict[str, Any], existing: list[dict[str, Any]], correlation_id: str) -> dict[str, Any]:
        title = _clean(item.get("title")); description = _clean(item.get("description")); criteria = _criteria(item.get("acceptanceCriteria"))
        normalized_title = _title_case(title) or "Untitled Requirement"
        business_goal = _business_goal(description, title)
        problem = _problem_statement(description, title)
        ambiguity = _ambiguities(f"{title} {description} {' '.join(criteria)}")
        missing = _missing(title, description, criteria, business_goal, problem)
        ac_quality = _acceptance_quality(criteria)
        duplicates = _duplicates(item, existing)
        capabilities = [entry["name"] for entry in planning.get("selectedCapabilities", [])]
        if not capabilities:
            capabilities = [_capability_from_title(normalized_title)]
        dependencies = [entry["name"] for entry in planning.get("selectedDependencies", [])]
        risks = _risks(missing, ambiguity, ac_quality, context, duplicates)
        quality = _quality_score(title, description, missing, ambiguity, ac_quality)
        repository_mode = _repository_mode(context)
        repository_penalty = .08 if repository_mode == "Unavailable" else .03 if repository_mode == "KnowledgeSnapshot" else 0
        confidence = round(max(0.2, min(0.98, float(planning.get("confidence") or 0.45) * .45 + float(context.get("confidence") or 0.45) * .35 + quality / 100 * .2 - repository_penalty)), 2)
        analysis_id = f"wia-{uuid4().hex}"
        return {
            "analysisId": analysis_id, "workItemId": str(item.get("workItemId") or item.get("id") or ""),
            "workItemRevision": int(item.get("revision") or 0), "workItemType": str(item.get("workItemType") or item.get("type") or "Requirement"),
            "projectId": project_id, "qualityScore": quality, "normalizedTitle": normalized_title,
            "businessGoal": business_goal, "problemStatement": problem, "missingInformation": missing,
            "ambiguityFindings": ambiguity, "capabilityRecommendations": capabilities,
            "decompositionRecommendations": _decomposition(item, criteria, capabilities),
            "acceptanceCriteriaQuality": ac_quality, "duplicateOrSimilarWork": duplicates,
            "dependencies": dependencies, "risk": risks, "storyPointRecommendation": _story_points(criteria, dependencies, risks, missing),
            "confidence": confidence, "evidence": _evidence(context, planning),
            "status": "NeedsReview" if quality < 75 or confidence < .7 else "Ready",
            "context": {"capsuleId": context.get("capsuleId"), "capsuleVersion": context.get("capsuleVersion"), "repositoryMode": repository_mode, "knowledgeVersion": context.get("knowledgeVersion"), "memoryVersion": context.get("engineeringMemoryVersion"), "selectedContextCount": len(context.get("selectedContext") or []), "rejectedContext": [*(context.get("rejectedContext") or []), *(planning.get("rejectedContext") or [])], "tokenBudget": context.get("tokenBudget")},
            "planningContextVersion": "planning-intelligence", "correlationId": correlation_id, "createdAt": now_iso(),
        }

    def _recommendations(self, analysis: dict[str, Any], item: dict[str, Any]) -> list[WorkItemRecommendation]:
        specs = [
            ("NormalizedTitle", item.get("title"), analysis["normalizedTitle"], "Normalize the title into a concise, outcome-oriented form."),
            ("BusinessGoal", "", analysis["businessGoal"], "Make the intended business outcome explicit."),
            ("ProblemStatement", "", analysis["problemStatement"], "State the operational problem independently from the solution."),
            ("MissingInformation", [], analysis["missingInformation"], "Resolve missing information before automation."),
            ("AcceptanceCriteriaQuality", item.get("acceptanceCriteria"), analysis["acceptanceCriteriaQuality"], "Make acceptance criteria measurable and verifiable."),
            ("CapabilityRecommendations", [], analysis["capabilityRecommendations"], "Use only capabilities supported by Planning Context."),
            ("DecompositionRecommendations", [], analysis["decompositionRecommendations"], "Decompose along supported parent intent and acceptance boundaries."),
            ("Dependencies", [], analysis["dependencies"], "Include only dependencies supported by orchestrated evidence."),
            ("Risk", [], analysis["risk"], "Address requirement and delivery risks before write-back."),
            ("StoryPointRecommendation", None, analysis["storyPointRecommendation"], "Estimate from scope, criteria, dependencies, risks, and uncertainty."),
        ]
        if analysis["duplicateOrSimilarWork"]:
            specs.append(("DuplicateOrSimilarWork", [], analysis["duplicateOrSimilarWork"], "Review similar synchronized work before creating another item."))
        status = RecommendationStatus.NEEDS_REVIEW if analysis["status"] == "NeedsReview" else RecommendationStatus.DRAFT
        return [WorkItemRecommendation(
            recommendation_id=f"wir-{uuid4().hex}", work_item_id=analysis["workItemId"], work_item_revision=analysis["workItemRevision"],
            recommendation_type=kind, current_value=current, proposed_value=proposed, reasons=[reason],
            evidence=analysis["evidence"][:12], confidence=analysis["confidence"], status=status,
            analysis_id=analysis["analysisId"], project_id=analysis["projectId"],
        ) for kind, current, proposed, reason in specs]

    def _active_recommendation(self, recommendation_id: str) -> WorkItemRecommendation:
        item = self.repository.get(recommendation_id)
        if not item:
            raise RecommendationNotFoundError(recommendation_id)
        current = self.ado_sdk.find_cached("workItems", item.work_item_id, item.project_id)
        if current and int(current[1].get("revision") or 0) != item.work_item_revision:
            item.status = RecommendationStatus.STALE
            self.repository.save(item)
        if item.status == RecommendationStatus.STALE:
            raise StaleRecommendationError(recommendation_id)
        return item

    def _event(self, event_type: str, payload: dict[str, Any], correlation_id: str) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "ADOIntelligence", "projectId": payload.get("projectId"), "correlationId": correlation_id or payload.get("correlationId"), "payload": payload})


def _context_artifact(item: dict[str, Any], knowledge: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    return {"artifactId": str(item.get("workItemId") or item.get("id") or ""), "artifactType": str(item.get("workItemType") or "Requirement"), "title": _clean(item.get("title")), "description": _clean(item.get("description")), "acceptanceCriteria": _criteria(item.get("acceptanceCriteria")), "knowledgeRegistry": _compact_registry(knowledge), "knowledgeVersion": profile.get("knowledge_version") or profile.get("knowledgeVersion") or ""}


def _compact_registry(value: dict[str, Any]) -> dict[str, Any]:
    return {key: list(value.get(key) or [])[:30] for key in ("modules", "flows", "applications", "standards", "components", "architecture_notes")}


def _capsule_inputs(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry = {"modules": [], "flows": [], "applications": [], "standards": [], "components": [], "architecture_notes": []}
    repository = {"modules": [], "flows": [], "dependencies": [], "files": []}
    keys = {"Module": "modules", "Flow": "flows", "Application": "applications", "Standard": "standards", "Component": "components", "Architecture": "architecture_notes"}
    for item in context.get("selectedContext") or []:
        source = item.get("sourceType"); category = item.get("category"); title = item.get("title") or item.get("content")
        if source == "KnowledgeRegistry" and category in keys and title:
            registry[keys[category]].append(title)
        if source == "Repository" and title:
            if category == "Module": repository["modules"].append(title)
            elif category == "Flow": repository["flows"].append(title)
            else: repository["files"].append({"path": title, "confidence": item.get("confidenceScore"), "evidence": item.get("provenance")})
    return {"knowledgeRegistry": registry, "repositorySnapshot": repository}


def _planning_work_item(item: dict[str, Any]) -> dict[str, Any]:
    return {"id": item.get("workItemId") or item.get("id"), "type": item.get("workItemType") or item.get("type"), "title": _clean(item.get("title")), "description": _clean(item.get("description")), "acceptanceCriteria": _criteria(item.get("acceptanceCriteria"))}


def _repository_id(profile: dict[str, Any], cache: dict[str, Any]) -> str:
    connection = profile.get("repository_connection") if isinstance(profile.get("repository_connection"), dict) else {}
    if connection.get("repository_id"):
        return str(connection["repository_id"])
    repositories = cache.get("repositories", {}) if isinstance(cache.get("repositories"), dict) else {}
    return str(next(iter(repositories), ""))


def _clean(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, list): return " ".join(_clean(x) for x in value if _clean(x))
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(str(value))).split())


def _criteria(value: Any) -> list[str]:
    if isinstance(value, list): return [_clean(x) for x in value if _clean(x)]
    text = html.unescape(str(value or "")).replace("</li>", "\n").replace("<br>", "\n").replace("<br/>", "\n")
    return [cleaned for part in re.split(r"[\r\n]+|(?=\b(?:Given|When|Then)\b)", text) if (cleaned := _clean(part).lstrip("-•0123456789. "))]


def _title_case(value: str) -> str:
    minor = {"a", "an", "and", "for", "in", "of", "on", "the", "to"}
    return " ".join(word.lower() if index and word.lower() in minor else word[:1].upper() + word[1:] for index, word in enumerate(value.split()))


def _business_goal(description: str, title: str) -> str:
    selected = next((sentence for sentence in re.split(r"(?<=[.!?])\s+", description) if any(key in sentence.lower() for key in ("goal", "outcome", "value", "so that", "reduce", "increase", "improve"))), "")
    return selected or f"Deliver {title.lower()} with a measurable operational outcome."


def _problem_statement(description: str, title: str) -> str:
    selected = next((sentence for sentence in re.split(r"(?<=[.!?])\s+", description) if any(key in sentence.lower() for key in ("problem", "cannot", "unable", "lack", "difficult", "because"))), "")
    return selected or f"The current process does not clearly support {title.lower()}."


def _ambiguities(corpus: str) -> list[dict[str, str]]:
    lower = corpus.lower()
    return [{"term": term, "finding": f"'{term}' is not measurable or sufficiently specific."} for term in sorted(AMBIGUOUS) if term in lower]


def _missing(title: str, description: str, criteria: list[str], goal: str, problem: str) -> list[str]:
    missing = []
    if len(title.split()) < 3: missing.append("Outcome-oriented title")
    if len(description.split()) < 12: missing.append("Detailed requirement description")
    if not criteria: missing.append("Acceptance criteria")
    if goal.startswith("Deliver "): missing.append("Explicit business goal")
    if problem.startswith("The current process"): missing.append("Explicit problem statement")
    if not any(any(token in criterion.lower() for token in ("within", "less than", "at least", "must", "denied", "error", "display")) for criterion in criteria): missing.append("Measurable validation conditions")
    return missing


def _acceptance_quality(criteria: list[str]) -> dict[str, Any]:
    if not criteria:
        return {"score": 0, "status": "Missing", "criteriaCount": 0, "fragmentedCriteria": [], "findings": ["No acceptance criteria were supplied."]}
    fragments = [item for item in criteria if len(item.split()) < 4]
    measurable = sum(any(token in item.lower() for token in ("must", "within", "at least", "displays", "returns", "denied", "error", "given", "when", "then")) for item in criteria)
    score = max(20, min(100, round(45 + 45 * measurable / len(criteria) - 8 * len(fragments))))
    return {"score": score, "status": "Strong" if score >= 80 else "NeedsReview", "criteriaCount": len(criteria), "fragmentedCriteria": fragments, "findings": [] if score >= 80 else ["Add measurable outcomes and combine fragmented acceptance criteria."]}


def _duplicates(item: dict[str, Any], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    title = _clean(item.get("title")).lower(); tokens = set(re.findall(r"[a-z0-9]+", title)); output = []
    for candidate in existing:
        other = _clean(candidate.get("title")).lower(); other_tokens = set(re.findall(r"[a-z0-9]+", other))
        score = max(len(tokens & other_tokens) / max(1, len(tokens | other_tokens)), SequenceMatcher(None, title, other).ratio())
        if score >= .62:
            output.append({"workItemId": candidate.get("workItemId") or candidate.get("id"), "title": candidate.get("title"), "confidence": round(score, 2), "reason": "Title and intent overlap with synchronized work."})
    return sorted(output, key=lambda entry: entry["confidence"], reverse=True)[:5]


def _capability_from_title(title: str) -> str:
    return re.sub(r"^(Add|Build|Create|Implement|Modernize|Update)\s+", "", title, flags=re.I) or "Requirement Clarification"


def _decomposition(item: dict[str, Any], criteria: list[str], capabilities: list[str]) -> list[str]:
    kind = str(item.get("workItemType") or "Requirement").lower()
    if kind == "epic": return [f"Create one Feature for the {capability} capability." for capability in capabilities[:8]]
    if kind == "feature": return [f"Create an independently testable Story for: {criterion}" for criterion in criteria[:8]] or ["Identify user actions before generating Stories."]
    return [f"Map implementation and test work to acceptance criterion {index + 1}." for index in range(max(1, len(criteria)))]


def _risks(missing: list[str], ambiguity: list[dict], ac: dict[str, Any], context: dict[str, Any], duplicates: list[dict]) -> list[dict[str, str]]:
    risks = []
    if missing: risks.append({"level": "High", "type": "Requirement", "reason": f"Missing: {', '.join(missing)}"})
    if ambiguity: risks.append({"level": "Medium", "type": "Ambiguity", "reason": "Ambiguous language may produce inconsistent implementation."})
    if ac["score"] < 70: risks.append({"level": "High", "type": "Validation", "reason": "Acceptance criteria are not sufficiently verifiable."})
    if _repository_mode(context) == "Unavailable": risks.append({"level": "Medium", "type": "Repository", "reason": "Repository Intelligence is unavailable; confidence is reduced."})
    if duplicates: risks.append({"level": "Medium", "type": "Duplication", "reason": "Similar synchronized work exists."})
    return risks or [{"level": "Low", "type": "Requirement", "reason": "No material requirement risks detected."}]


def _quality_score(title: str, description: str, missing: list[str], ambiguity: list[dict], ac: dict[str, Any]) -> int:
    score = (15 if len(title.split()) >= 3 else 7) + min(30, len(description.split())) + round(ac["score"] * .45)
    return max(0, min(100, score - min(20, len(missing) * 4 + len(ambiguity) * 3)))


def _story_points(criteria: list[str], dependencies: list[str], risks: list[dict], missing: list[str]) -> dict[str, Any]:
    complexity = len(criteria) + len(dependencies) + 2 * sum(r["level"] in {"High", "Critical"} for r in risks) + len(missing)
    return {"points": FIBONACCI[min(len(FIBONACCI) - 1, complexity // 3)], "confidence": round(max(.35, .9 - .06 * len(missing)), 2), "reason": "Based on acceptance scope, dependencies, risks, and unresolved information."}


def _evidence(context: dict[str, Any], planning: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = [{"source": item.get("sourceType"), "type": item.get("category"), "value": item.get("title"), "reason": "; ".join(item.get("reasons") or []) or "Selected by Context Orchestrator."} for item in context.get("selectedContext") or []]
    for key, source_type in (("selectedCapabilities", "Capability"), ("selectedModules", "Module"), ("selectedFlows", "Flow")):
        evidence.extend({"source": entry.get("source"), "type": source_type, "value": entry.get("name"), "reason": entry.get("reason")} for entry in planning.get(key) or [])
    unique = {}
    for item in evidence:
        if item.get("value"): unique.setdefault((str(item["source"]), str(item["type"]), str(item["value"])), item)
    return list(unique.values())


def _repository_mode(context: dict[str, Any]) -> str:
    repository_diagnostics = ((context.get("diagnostics") or {}).get("sources") or {}).get("Repository") or {}
    explicit = repository_diagnostics.get("repositoryMode")
    if explicit in {"CodeIndexed", "KnowledgeSnapshot", "Unavailable"}:
        return explicit
    for source in context.get("sourceSummary") or []:
        if source.get("sourceType") == "Repository":
            if not source.get("available"): return "Unavailable"
            return "CodeIndexed" if source.get("selectedCount") else "KnowledgeSnapshot"
    return "Unavailable"
