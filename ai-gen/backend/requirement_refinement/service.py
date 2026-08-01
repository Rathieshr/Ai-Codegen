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
        if existing and not force and existing.get("sourceContentHash") == requirement.get("contentHash"):
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
            requirement_summary=_text(value.get("requirementSummary")) or _summary(original),
            business_objective=_text(value.get("businessObjective")),
            problem_statement=_text(value.get("problemStatement")),
            user_intent=_text(value.get("userIntent")) or original,
            primary_actor=_text(value.get("primaryActor")),
            secondary_actors=_strings(value.get("secondaryActors")),
            core_capability=_text(value.get("coreCapability")),
            expected_outcome=_text(value.get("expectedOutcome")),
            potential_domain_terms=_strings(value.get("potentialDomainTerms")),
            potential_search_keywords=_strings(value.get("potentialSearchKeywords")) or list(intent.get("keywords") or []),
            potential_repository_terms=_strings(value.get("potentialRepositoryTerms")) or list(intent.get("repositoryHints") or []),
            potential_azure_devops_terms=_strings(value.get("potentialAzureDevOpsTerms")) or list(intent.get("azureDevOpsHints") or []),
            potential_markdown_terms=_strings(value.get("potentialMarkdownTerms")) or list(intent.get("markdownHints") or []),
            requirement_intent=intent,
            changes=_changes(value.get("changes"), original, _text(value.get("refinedRequirement")) or original),
            reasoning=_strings(value.get("reasoning")) or _strings(reasoning.get("reasoning")),
            ambiguities=_strings(value.get("ambiguities")),
            clarification_candidates=_strings(value.get("clarificationCandidates")),
            confidence=_confidence(value.get("confidence"), reasoning.get("confidence")),
            status="PendingReview",
            provider=_text(reasoning.get("provider")) or "Deterministic",
            model=_text(reasoning.get("model")),
            prompt_version=_text(reasoning.get("promptVersion")) or "requirement-refinement-v1",
            version=version,
            generated_at=now,
            revision_history=history,
            warnings=warnings,
        ).to_dict()
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
        return not any(term in output and term not in source for term in _FORBIDDEN_IMPLICIT_TERMS)

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
    refined = original
    if original and len(original.split()) < 8:
        verb = "Implement" if re.match(r"^(need|add|build|create)\b", original, re.I) else "Support"
        subject = re.sub(r"^(need|add|build|create)\s+", "", original, flags=re.I).rstrip(". ")
        refined = f"{verb} {subject}." if subject else original
    return {
        "refinedRequirement": refined,
        "requirementSummary": title or _summary(original),
        "businessObjective": "",
        "problemStatement": original,
        "userIntent": original,
        "primaryActor": "",
        "coreCapability": title,
        "expectedOutcome": "",
        "changes": [],
        "reasoning": ["Normalized wording while preserving the source requirement."],
        "ambiguities": [],
        "clarificationCandidates": [],
        "confidence": 0.6,
        "requirementIntent": {},
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
        "keywords": keywords,
        "repositoryHints": _strings(source.get("repositoryHints")),
        "markdownHints": _strings(source.get("markdownHints")),
        "azureDevOpsHints": _strings(source.get("azureDevOpsHints")),
        "clarificationCandidates": _strings(source.get("clarificationCandidates") or refinement.get("clarificationCandidates")),
        "confidence": _confidence(source.get("confidence"), refinement.get("confidence")),
    }


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
    return {"reasoningMode": "Deterministic", "provider": "Deterministic", "warnings": [warning]}


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
