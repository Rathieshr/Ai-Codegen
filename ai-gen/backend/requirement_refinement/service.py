"""Provider-backed, auditable requirement refinement before engineering discovery."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.platform.shared import JsonMapStore
from backend.requirement_intake import RequirementIngestionService

from .models import RequirementRefinement


_FORBIDDEN_IMPLICIT_TERMS = {
    "authentication", "authorization", "audit", "cache", "caching", "database",
    "notification", "notifications", "retry", "role management", "validation",
}

_ACTION_FAMILIES = {
    "view": "observe", "show": "observe", "display": "observe", "see": "observe",
    "search": "find", "find": "find", "locate": "find",
    "identify": "identify", "detect": "identify",
    "monitor": "monitor", "track": "monitor",
    "manage": "manage", "update": "update", "delete": "delete", "create": "create",
    "export": "export", "import": "import", "notify": "notify", "calculate": "calculate",
    "filter": "filter", "approve": "approve", "reject": "reject", "submit": "submit",
}


class RequirementRefinementService:
    """Improves wording without discovering or inventing engineering facts."""

    def __init__(
        self,
        store: JsonMapStore,
        *,
        requirement_ingestion: RequirementIngestionService,
        reasoning_engine: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.requirement_ingestion = requirement_ingestion
        self.reasoning_engine = reasoning_engine
        self.platform = platform

    def refine(self, requirement_id: str, *, force: bool = False) -> dict[str, Any]:
        requirement = self.requirement_ingestion.get(requirement_id)
        if not requirement:
            raise ValueError("Requirement context was not found. Ingest the source before refinement.")
        existing = self.get(requirement_id)
        if (
            existing and not force
            and existing.get("sourceContentHash") == requirement.get("contentHash")
            and existing.get("schemaVersion") == "RequirementRefinementV2"
        ):
            return existing

        original = _text(requirement.get("normalizedRequirement"))
        reasoning = self._reason(requirement)
        candidate = self._candidate(reasoning)
        warnings = list(reasoning.get("warnings") or [])
        if not self._safe(candidate, original):
            warnings.append("Provider refinement introduced unsupported functionality and was rejected.")
            candidate = {}
        deterministic = _deterministic_refinement(requirement)
        value = {**deterministic, **{key: item for key, item in candidate.items() if item not in (None, "", [])}}
        intent = _normalize_intent(value.get("requirementIntent"), value, original)
        business_goal = _distinct_business_goal(value, intent, original)
        core_capabilities = _strings(value.get("coreCapabilities")) or _strings(intent.get("capabilities"))
        if not core_capabilities and _text(value.get("coreCapability")):
            core_capabilities = [_text(value.get("coreCapability"))]
        business_entities = _strings(value.get("businessEntities")) or _strings(intent.get("entities"))
        engineering_concepts = _strings(value.get("engineeringConcepts")) or _strings(intent.get("concepts"))
        domain_terminology = _strings(value.get("domainTerminology")) or _strings(value.get("potentialDomainTerms"))
        repository_hints = _strings(value.get("repositorySearchHints")) or _strings(value.get("potentialRepositoryTerms")) or list(intent.get("repositoryHints") or [])
        markdown_hints = _strings(value.get("markdownSearchHints")) or _strings(value.get("potentialMarkdownTerms")) or list(intent.get("markdownHints") or [])
        azure_devops_hints = _strings(value.get("azureDevOpsSearchHints")) or _strings(value.get("potentialAzureDevOpsTerms")) or list(intent.get("azureDevOpsHints") or [])
        now = _now()
        version = int(existing.get("version") or 0) + 1 if existing else 1
        history = list(existing.get("revisionHistory") or []) if existing else []
        if existing:
            history.append({
                "version": existing.get("version"),
                "refinedRequirement": existing.get("refinedRequirement"),
                "status": existing.get("status"),
                "provider": existing.get("provider"),
                "model": existing.get("model"),
                "timestamp": existing.get("generatedAt"),
            })
        record = RequirementRefinement(
            refinement_id=str(existing.get("refinementId") or f"refinement_{uuid4().hex}") if existing else f"refinement_{uuid4().hex}",
            requirement_id=requirement_id,
            original_requirement=original,
            refined_requirement=_text(value.get("refinedRequirement")) or original,
            executive_summary=_text(value.get("executiveSummary") or value.get("requirementSummary")) or _summary(original),
            requirement_summary=_text(value.get("requirementSummary")) or _summary(original),
            business_goal=business_goal,
            business_objective=business_goal,
            problem_statement=_text(value.get("problemStatement")),
            user_intent=_text(value.get("userIntent")) or original,
            primary_actor=_text(value.get("primaryActor")),
            secondary_actors=_strings(value.get("secondaryActors")),
            core_capability=_text(value.get("coreCapability")),
            core_capabilities=core_capabilities,
            expected_outcome=_text(value.get("expectedOutcome")),
            business_entities=business_entities,
            engineering_concepts=engineering_concepts,
            domain_terminology=domain_terminology,
            repository_search_hints=repository_hints,
            markdown_search_hints=markdown_hints,
            azure_devops_search_hints=azure_devops_hints,
            possible_module_names=_strings(value.get("possibleModuleNames")),
            possible_feature_names=_strings(value.get("possibleFeatureNames")),
            potential_domain_terms=domain_terminology,
            potential_search_keywords=_strings(value.get("potentialSearchKeywords")) or list(intent.get("keywords") or []),
            potential_repository_terms=repository_hints,
            potential_azure_devops_terms=azure_devops_hints,
            potential_markdown_terms=markdown_hints,
            requirement_intent=intent,
            changes=_changes(value.get("changes"), original, _text(value.get("refinedRequirement")) or original),
            reasoning=_strings(value.get("reasoning")) or _strings(reasoning.get("reasoning")),
            ambiguities=_strings(value.get("ambiguities")),
            clarification_candidates=_strings(value.get("clarificationCandidates")),
            confidence=_confidence(value.get("confidence"), reasoning.get("confidence")),
            status="PendingReview",
            provider=_text(reasoning.get("provider")) or "Deterministic",
            model=_text(reasoning.get("model")),
            prompt_version=_text(reasoning.get("promptVersion")) or "requirement-refinement-v2:deterministic",
            version=version,
            generated_at=now,
            revision_history=history,
            warnings=warnings,
        ).to_dict()
        record["schemaVersion"] = "RequirementRefinementV2"
        record["sourceContentHash"] = requirement.get("contentHash")
        self._save(requirement_id, record)
        self._publish("RequirementRefined", record, requirement)
        return record

    def get(self, requirement_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(requirement_id)
        return dict(value) if isinstance(value, dict) else None

    def accept(self, requirement_id: str, actor: str) -> dict[str, Any]:
        value = self.refine(requirement_id)
        value.update({"status": "Accepted", "acceptedBy": actor or "HEI User", "acceptedAt": _now()})
        self._save(requirement_id, value)
        self._publish("RequirementRefinementAccepted", value, self.requirement_ingestion.get(requirement_id) or {})
        return value

    def edit(self, requirement_id: str, refined_requirement: str, actor: str) -> dict[str, Any]:
        value = self.refine(requirement_id)
        refined = _text(refined_requirement)
        if not refined:
            raise ValueError("Refined requirement is required.")
        history = list(value.get("revisionHistory") or [])
        history.append({
            "version": value.get("version"), "refinedRequirement": value.get("refinedRequirement"),
            "status": value.get("status"), "provider": value.get("provider"),
            "model": value.get("model"), "timestamp": value.get("generatedAt"),
        })
        intent = dict(value.get("requirementIntent") or {})
        intent.update({
            "functionalIntent": [refined],
            "keywords": _keywords(refined),
            "clarificationCandidates": [],
            "confidence": 1.0,
        })
        value.update({
            "refinedRequirement": refined,
            "requirementIntent": intent,
            "potentialSearchKeywords": list(intent["keywords"]),
            "status": "Accepted",
            "acceptedBy": actor or "HEI User",
            "acceptedAt": _now(),
            "version": int(value.get("version") or 1) + 1,
            "revisionHistory": history,
            "changes": _changes([], value.get("originalRequirement") or "", refined),
        })
        self._save(requirement_id, value)
        self._publish("RequirementRefinementEdited", value, self.requirement_ingestion.get(requirement_id) or {})
        return value

    def skip(self, requirement_id: str, actor: str) -> dict[str, Any]:
        value = self.refine(requirement_id)
        value.update({
            "status": "Skipped", "acceptedBy": actor or "HEI User", "acceptedAt": _now(),
            "refinedRequirement": value.get("originalRequirement") or "",
            "warnings": [*list(value.get("warnings") or []), "Refinement was skipped by the user; analysis uses the original requirement."],
        })
        self._save(requirement_id, value)
        self._publish("RequirementRefinementSkipped", value, self.requirement_ingestion.get(requirement_id) or {})
        return value

    def canonical_requirement(self, requirement_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        requirement = self.requirement_ingestion.get(requirement_id)
        if not requirement:
            raise ValueError("Requirement context was not found.")
        refinement = self.refine(requirement_id)
        canonical = dict(requirement)
        canonical["originalRequirement"] = requirement.get("normalizedRequirement")
        canonical["normalizedRequirement"] = (
            refinement.get("originalRequirement")
            if refinement.get("status") == "Skipped"
            else refinement.get("refinedRequirement")
        ) or requirement.get("normalizedRequirement")
        canonical["requirementIntent"] = dict(refinement.get("requirementIntent") or {})
        canonical["refinementId"] = refinement.get("refinementId")
        canonical["refinementVersion"] = refinement.get("version")
        canonical["refinementStatus"] = refinement.get("status")
        return canonical, refinement

    def _reason(self, requirement: dict[str, Any]) -> dict[str, Any]:
        if not self.reasoning_engine:
            return _fallback("Reasoning AI was not configured for requirement refinement.")
        metadata = requirement.get("metadata") or {}
        attributes = metadata.get("attributes") or {}
        context = {
            "contextType": "RequirementRefinementInput",
            "contextId": f"requirement-refinement-{requirement.get('requirementId')}",
            "contextVersion": requirement.get("contextVersion") or "1.0",
            "requirement": {
                "requirementId": requirement.get("requirementId"),
                "title": requirement.get("title"),
                "sourceType": requirement.get("sourceType"),
                "normalizedRequirement": requirement.get("normalizedRequirement"),
            },
            "metadata": {
                "projectId": metadata.get("projectId"),
                "projectName": metadata.get("projectName"),
                "product": attributes.get("product"),
                "domain": attributes.get("domain"),
                "terminology": attributes.get("terminology") or [],
            },
        }
        try:
            return self.reasoning_engine.refine(
                "Requirement Refinement", context,
                user_requirement=_text(requirement.get("normalizedRequirement")),
                provider="Auto", correlation_id=_text(requirement.get("correlationId")),
            )
        except Exception as error:
            return _fallback(f"Requirement refinement provider unavailable: {error}")

    @staticmethod
    def _candidate(reasoning: dict[str, Any]) -> dict[str, Any]:
        recommendation = reasoning.get("recommendation")
        if not isinstance(recommendation, dict):
            return {}
        candidate = recommendation.get("refinement") or recommendation
        return dict(candidate) if isinstance(candidate, dict) else {}

    @staticmethod
    def _safe(candidate: dict[str, Any], original: str) -> bool:
        refined = _text(candidate.get("refinedRequirement"))
        if not refined:
            return True
        source = original.casefold()
        output = refined.casefold()
        if any(term in output and term not in source for term in _FORBIDDEN_IMPLICIT_TERMS):
            return False
        source_actions = _semantic_actions(source)
        output_actions = _semantic_actions(output)
        return output_actions.issubset(source_actions)

    def _save(self, requirement_id: str, value: dict[str, Any]) -> None:
        values = self.store.read()
        values[requirement_id] = value
        self.store.write(values)

    def _publish(self, name: str, value: dict[str, Any], requirement: dict[str, Any]) -> None:
        if self.platform and hasattr(self.platform, "publish_event"):
            self.platform.publish_event(name, {
                "requirementId": value.get("requirementId"),
                "refinementId": value.get("refinementId"),
                "version": value.get("version"),
                "status": value.get("status"),
                "correlationId": requirement.get("correlationId"),
            })


def _deterministic_refinement(requirement: dict[str, Any]) -> dict[str, Any]:
    original = _text(requirement.get("normalizedRequirement"))
    title = _text(requirement.get("title"))
    refined = _rewrite_for_clarity(original)
    primary_actor = _extract_actor(original)
    entities = _business_entities(original)
    capabilities = _capability_candidates(original, title, entities)
    terms = _unique([*entities, *capabilities, *_keywords(original)])
    expected_outcome = _expected_outcome(original)
    business_goal = _business_goal_from_source(original, expected_outcome)
    user_intent = re.split(r"\s+so\s+that\s+", original, maxsplit=1, flags=re.I)[0].rstrip(". ")
    clarification_candidates = []
    if not primary_actor:
        clarification_candidates.append("Who is the primary user or business actor for this requirement?")
    if not expected_outcome:
        clarification_candidates.append("What observable business outcome should this requirement achieve?")
    return {
        "refinedRequirement": refined,
        "executiveSummary": title or _summary(refined),
        "requirementSummary": title or _summary(original),
        "businessGoal": business_goal,
        "businessObjective": business_goal,
        "problemStatement": original,
        "userIntent": user_intent,
        "primaryActor": primary_actor,
        "secondaryActors": [],
        "coreCapability": capabilities[0] if capabilities else title,
        "coreCapabilities": capabilities,
        "expectedOutcome": expected_outcome,
        "businessEntities": entities,
        "engineeringConcepts": capabilities,
        "domainTerminology": entities,
        "repositorySearchHints": terms[:12],
        "markdownSearchHints": _unique([title, *entities, *capabilities])[:12],
        "azureDevOpsSearchHints": _unique([title, *capabilities, *entities])[:12],
        "possibleModuleNames": capabilities[:8],
        "possibleFeatureNames": capabilities[:8],
        "potentialDomainTerms": entities,
        "potentialSearchKeywords": _keywords(original),
        "potentialRepositoryTerms": terms[:12],
        "potentialMarkdownTerms": _unique([title, *entities, *capabilities])[:12],
        "potentialAzureDevOpsTerms": _unique([title, *capabilities, *entities])[:12],
        "changes": _changes([], original, refined),
        "reasoning": [
            "Separated the user action from the expected business outcome.",
            "Derived search hints only from terminology present in the source requirement.",
        ],
        "ambiguities": [],
        "clarificationCandidates": clarification_candidates,
        "confidence": 0.6,
        "requirementIntent": {
            "businessGoal": business_goal,
            "functionalIntent": [user_intent] if user_intent else [],
            "entities": entities,
            "actions": _actions(original),
            "concepts": capabilities,
            "capabilities": capabilities,
            "keywords": _keywords(original),
            "repositoryHints": terms[:12],
            "markdownHints": _unique([title, *entities, *capabilities])[:12],
            "azureDevOpsHints": _unique([title, *capabilities, *entities])[:12],
            "clarificationCandidates": clarification_candidates,
            "confidence": 0.6,
        },
    }


def _normalize_intent(value: Any, refinement: dict[str, Any], original: str) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    keywords = _strings(source.get("keywords")) or _keywords(original)
    return {
        "businessGoal": _text(source.get("businessGoal") or refinement.get("businessObjective")),
        "functionalIntent": _strings(source.get("functionalIntent")) or [_text(refinement.get("userIntent") or original)],
        "entities": _strings(source.get("entities")),
        "actions": _strings(source.get("actions")),
        "concepts": _strings(source.get("concepts")),
        "capabilities": _strings(source.get("capabilities") or refinement.get("coreCapabilities")),
        "keywords": keywords,
        "repositoryHints": _strings(source.get("repositoryHints")),
        "markdownHints": _strings(source.get("markdownHints")),
        "azureDevOpsHints": _strings(source.get("azureDevOpsHints")),
        "clarificationCandidates": _strings(source.get("clarificationCandidates") or refinement.get("clarificationCandidates")),
        "confidence": _confidence(source.get("confidence"), refinement.get("confidence")),
    }


def _distinct_business_goal(value: dict[str, Any], intent: dict[str, Any], original: str) -> str:
    goal = _text(value.get("businessGoal") or value.get("businessObjective") or intent.get("businessGoal"))
    functional = " ".join(_strings(intent.get("functionalIntent")) or [_text(value.get("userIntent"))])
    if goal and goal.casefold() != functional.casefold():
        return goal
    outcome = _text(value.get("expectedOutcome")) or _expected_outcome(original)
    if outcome and outcome.casefold() != functional.casefold():
        return outcome[0].upper() + outcome[1:]
    return ""


def _rewrite_for_clarity(original: str) -> str:
    if not original:
        return ""
    view = re.match(
        r"^provide\s+(.+?)\s+with\s+(?:an?\s+)?real[- ]time\s+view\s+of\s+(.+?)"
        r"\s+so\s+that\s+(.+?)[.]?$",
        original,
        re.I,
    )
    if view:
        actor, subject, outcome = view.groups()
        passive = re.match(r"^(.+?)\s+can be identified and acted on\s+(.+)$", outcome, re.I)
        if passive:
            outcome = f"can identify and act on {passive.group(1).strip()} {passive.group(2).strip()}"
        return f"Enable {actor.strip()} to view {subject.strip()} in real time, so they {outcome.strip()}."
    if len(original.split()) < 8:
        verb = "Implement" if re.match(r"^(need|add|build|create)\b", original, re.I) else "Support"
        subject = re.sub(r"^(need|add|build|create)\s+", "", original, flags=re.I).rstrip(". ")
        return f"{verb} {subject}." if subject else original
    return original


def _extract_actor(value: str) -> str:
    framed = re.search(r"\b(?:provide|allow|enable)\s+(.+?\s+Users?)\b", value, re.I)
    if framed:
        return framed.group(1).strip()
    match = re.search(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\s+Users?)\b", value)
    return match.group(1).strip() if match else ""


def _expected_outcome(value: str) -> str:
    parts = re.split(r"\s+so\s+that\s+", value, maxsplit=1, flags=re.I)
    return parts[1].rstrip(". ") if len(parts) == 2 else ""


def _business_goal_from_source(value: str, outcome: str) -> str:
    if outcome:
        passive = re.match(r"^(.+?)\s+can be identified and acted on\s+(.+)$", outcome, re.I)
        if passive:
            return f"Identify and act on {passive.group(1).strip()} {passive.group(2).strip()}."
        normalized = re.sub(r"\bcan be\s+", "", outcome, flags=re.I)
        return normalized[0].upper() + normalized[1:] if normalized else ""
    match = re.search(r"\b(?:to|in order to)\s+(.+?)[.]?$", value, re.I)
    return match.group(1).strip().capitalize() if match else ""


def _business_entities(value: str) -> list[str]:
    source = re.sub(r"\s+so\s+that\s+.*$", "", value, flags=re.I)
    view = re.search(r"\b(?:view|display|summary|list)\s+of\s+(.+)$", source, re.I)
    if view:
        entities = _clean_entity_list(view.group(1))
        outcome_entity = re.search(r"\b(.+?)\s+can be (?:identified|detected|monitored)\b", _expected_outcome(value), re.I)
        return _unique([*entities, *(outcome_entity.groups() if outcome_entity else ())])
    action = re.search(r"\b(?:search|monitor|manage|identify|review|detect|view)\s+(.+)$", source, re.I)
    if action:
        return _clean_entity_list(action.group(1))
    nominalized = re.search(
        r"\b(.+?)\s+(?:search|monitoring|management|visibility|detection|review)\b",
        source,
        re.I,
    )
    if nominalized:
        subject = re.sub(r"^(?:need|support|implement|add|build|create)\s+", "", nominalized.group(1), flags=re.I)
        return _clean_entity_list(subject)
    return []


def _clean_entity_list(value: str) -> list[str]:
    items = re.split(r"\s*,\s*|\s*,?\s+and\s+", value)
    output = []
    for item in items:
        cleaned = re.sub(r"^(?:and|or)\s+", "", item.strip(), flags=re.I)
        cleaned = re.sub(r"^(?:a|an|the|current|real[- ]time)\s+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+(?:from|within|across)\s+.+$", "", cleaned, flags=re.I)
        if 1 <= len(cleaned.split()) <= 6:
            output.append(cleaned.rstrip(". "))
    return _unique(output)


def _actions(value: str) -> list[str]:
    patterns = (
        ("view", r"\b(?:view|display|show)\b"), ("search", r"\b(?:search|find|locate)\b"),
        ("monitor", r"\bmonitor(?:ed|ing)?\b"), ("manage", r"\bmanag(?:e|ed|ing)\b"),
        ("identify", r"\bidentif(?:y|ied|ication)\b"), ("review", r"\breview(?:ed|ing)?\b"),
        ("detect", r"\bdetect(?:ed|ion|ing)?\b"), ("act", r"\bact(?:ed|ion|ing)?\s+on\b"),
    )
    return [name for name, pattern in patterns if re.search(pattern, value, re.I)]


def _semantic_actions(value: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z]+", value.casefold()))
    return {family for word, family in _ACTION_FAMILIES.items() if word in words}


def _capability_candidates(value: str, title: str, entities: list[str]) -> list[str]:
    actions = _actions(value)
    suffix = {
        "view": "Visibility", "display": "Visibility", "search": "Search",
        "monitor": "Monitoring", "manage": "Management", "identify": "Identification",
        "detect": "Detection", "review": "Review", "act": "Response",
    }
    capabilities = []
    for action in actions:
        if action not in suffix:
            continue
        if action in {"identify", "detect", "act"}:
            subject = next((item for item in entities if re.search(r"\b(?:unhealthy|fault|issue|failure|risk)\b", item, re.I)), entities[-1] if entities else title)
        else:
            subject = entities[0] if entities else title
        if subject:
            capabilities.append(f"{subject.title()} {suffix[action]}")
    if not capabilities and title:
        capabilities.append(title)
    return _unique(capabilities)[:8]


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(_text(item) for item in values if _text(item)))


def _changes(value: Any, original: str, refined: str) -> list[dict[str, str]]:
    output = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict) and _text(item.get("change")):
            output.append({"change": _text(item.get("change")), "reason": _text(item.get("reason"))})
        elif _text(item):
            output.append({"change": _text(item), "reason": "Improved requirement clarity."})
    if not output and refined != original:
        output.append({"change": "Reworded the requirement for engineering clarity.", "reason": "Preserved intent without adding functionality."})
    return output


def _fallback(warning: str) -> dict[str, Any]:
    return {
        "reasoningMode": "Deterministic",
        "provider": "Deterministic",
        "promptVersion": "requirement-refinement-v2:deterministic",
        "warnings": [warning],
    }


def _summary(value: str) -> str:
    return value.split(".", 1)[0][:180].strip()


def _keywords(value: str) -> list[str]:
    ignored = {"about", "allow", "from", "have", "into", "need", "should", "that", "the", "their", "this", "with"}
    return list(dict.fromkeys(word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", value) if word.casefold() not in ignored))[:16]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(_text(item) for item in value if _text(item)))


def _confidence(primary: Any, secondary: Any = 0.0) -> float:
    value = primary if primary not in (None, "") else secondary
    if isinstance(value, dict):
        value = value.get("overall") or 0
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(1.0, number / 100 if number > 1 else number)), 2)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
