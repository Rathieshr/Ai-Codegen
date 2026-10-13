"""Statement-level governance for Requirement Intelligence."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class StatementClassification(str, Enum):
    SOURCE = "SOURCE"
    EVIDENCE = "EVIDENCE"
    AI_INFERRED = "AI_INFERRED"
    AI_SUGGESTION = "AI_SUGGESTION"
    UNKNOWN = "UNKNOWN"


_SUGGESTION_PATTERNS = {
    "rollback": "Rollback support is a common engineering enhancement but was not requested.",
    "retry": "Retry behavior is an implementation pattern that requires confirmation.",
    "authentication": "Authentication scope requires explicit requirement or engineering evidence.",
    "authorization": "Authorization scope requires explicit requirement or engineering evidence.",
    "permission": "Permission behavior requires explicit requirement or engineering evidence.",
    "audit": "Audit behavior requires explicit requirement or engineering evidence.",
    "notification": "Notification behavior requires explicit requirement or engineering evidence.",
    "role management": "Role management requires explicit requirement or engineering evidence.",
    "create read update delete": "CRUD scope must not be inferred from a general capability.",
    "crud": "CRUD scope must not be inferred from a general capability.",
}


class RequirementGovernanceEngine:
    """Separates facts, evidence, interpretations, suggestions, and unknowns."""

    def govern(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
        discovery: dict[str, Any],
        reasoning: dict[str, Any],
    ) -> dict[str, Any]:
        source_text = "\n".join(filter(None, [
            _text(requirement.get("title")),
            _text(requirement.get("normalizedRequirement")),
            _text(requirement.get("planningRequirement")),
        ]))
        report = dict(discovery.get("report") or {})
        evidence = _all_evidence(report)
        recommendation = reasoning.get("recommendation") if isinstance(reasoning.get("recommendation"), dict) else {}
        provider = _text(reasoning.get("provider")) or "Deterministic"
        model = _text(reasoning.get("model"))
        prompt_version = _text(reasoning.get("promptVersion"))
        generated_at = datetime.now(timezone.utc).isoformat()

        statements: list[dict[str, Any]] = []
        accepted_functional: list[str] = []
        suggested_enhancements: list[dict[str, Any]] = []
        for value in _unique(_strings(analysis.get("functionalRequirements"))):
            classification, matched, reason = self._classify_functional(value, source_text, evidence)
            statement = _statement(
                "Functional Requirement", value, classification, matched, reason,
                provider, model, prompt_version, generated_at,
            )
            statements.append(statement)
            if classification in {
                StatementClassification.SOURCE,
                StatementClassification.EVIDENCE,
                StatementClassification.AI_INFERRED,
            }:
                accepted_functional.append(value)
            else:
                suggested_enhancements.append({**statement, "requiresConfirmation": True})

        existing_suggestions = {item["text"] for item in suggested_enhancements}
        for candidate in recommendation.get("suggestedEnhancements") or []:
            value = _text(candidate.get("text") if isinstance(candidate, dict) else candidate)
            if not value or value in existing_suggestions:
                continue
            reason = (
                _text(candidate.get("reason"))
                if isinstance(candidate, dict)
                else "Provider proposed this as an optional enhancement."
            )
            item = _statement(
                "Suggested Enhancement", value, StatementClassification.AI_SUGGESTION,
                [], reason or "Provider proposed this as an optional enhancement.",
                provider, model, prompt_version, generated_at,
            )
            item["requiresConfirmation"] = True
            statements.append(item)
            suggested_enhancements.append(item)
            existing_suggestions.add(value)

        source_non_functional: list[str] = []
        candidate_non_functional: list[dict[str, Any]] = []
        non_functional = _unique(
            _strings(analysis.get("nonFunctionalRequirements"))
            + _strings(recommendation.get("candidateNonFunctionalRequirements"))
            + _strings(recommendation.get("nonFunctionalRequirements"))
        )
        for value in non_functional:
            if _supported(value, source_text):
                item = _statement(
                    "Non-Functional Requirement", value, StatementClassification.SOURCE,
                    ["source:requirement"], "Directly supported by the requirement source.",
                    provider, model, prompt_version, generated_at,
                )
                source_non_functional.append(value)
            else:
                matched = _matching_evidence(value, evidence)
                classification = StatementClassification.EVIDENCE if matched else StatementClassification.AI_SUGGESTION
                item = _statement(
                    "Candidate Non-Functional Requirement", value, classification, matched,
                    "Verified by engineering evidence." if matched else "Quality guidance requires explicit user approval.",
                    provider, model, prompt_version, generated_at,
                )
                if not matched:
                    item["requiresConfirmation"] = True
                candidate_non_functional.append(item)
            statements.append(item)

        business_goal = self._govern_business_goal(
            _text(recommendation.get("businessGoal")) or (_strings(analysis.get("businessGoals")) or [""])[0],
            source_text,
        )
        problem_statement = self._govern_problem_statement(
            _text(recommendation.get("problemStatement")), source_text,
        )
        business_value = self._govern_business_value(
            _text(recommendation.get("businessValue")), source_text,
        )
        primary_actor = _text(recommendation.get("primaryActor")) or (_strings(analysis.get("actors")) or [""])[0]
        if not primary_actor:
            primary_actor = _infer_actor(source_text)
        secondary_actors = _unique([
            *_strings(recommendation.get("secondaryActors")),
            *_strings(analysis.get("actors"))[1:],
        ])
        capabilities = _unique([
            *_strings(recommendation.get("capabilities")),
            *_strings((analysis.get("requirementIntent") or {}).get("capabilities")),
        ])

        governed_values = {
            "businessGoal": business_goal,
            "problemStatement": problem_statement,
            "businessValue": business_value,
            "primaryActor": primary_actor,
            "secondaryActors": secondary_actors,
            "capabilities": capabilities,
        }
        for category, value in (
            ("Business Goal", business_goal),
            ("Problem Statement", problem_statement),
            ("Business Value", business_value),
            ("Primary Actor", primary_actor),
        ):
            classification = (
                StatementClassification.SOURCE
                if category == "Primary Actor" and value and value.casefold() in source_text.casefold()
                else StatementClassification.AI_INFERRED if value
                else StatementClassification.UNKNOWN
            )
            statements.append(_statement(
                category,
                value,
                classification,
                ["source:requirement"] if value else [],
                _why(category, value), provider, model, prompt_version, generated_at,
            ))
        for value in secondary_actors:
            classification = StatementClassification.SOURCE if value.casefold() in source_text.casefold() else StatementClassification.AI_INFERRED
            statements.append(_statement(
                "Secondary Actor", value, classification,
                ["source:requirement"], "Plausible participant inferred from the requested workflow.",
                provider, model, prompt_version, generated_at,
            ))

        for category, key in (
            ("Business Rule", "businessRules"),
            ("Constraint", "constraints"),
            ("Dependency", "dependencies"),
        ):
            for value in _unique(_strings(analysis.get(key))):
                matched = _matching_evidence(value, evidence)
                if _supported(value, source_text):
                    classification = StatementClassification.SOURCE
                    references = ["source:requirement"]
                    reason = "Directly supported by the requirement source."
                elif matched:
                    classification = StatementClassification.EVIDENCE
                    references = matched
                    reason = "Verified by selected engineering evidence."
                else:
                    classification = StatementClassification.AI_SUGGESTION
                    references = []
                    reason = f"{category} is not supported by the source or selected evidence."
                item = _statement(
                    category, value, classification, references, reason,
                    provider, model, prompt_version, generated_at,
                )
                if classification == StatementClassification.AI_SUGGESTION:
                    item["requiresConfirmation"] = True
                    suggested_enhancements.append(item)
                statements.append(item)

        for category, key, classification in (
            ("Risk", "risks", StatementClassification.AI_INFERRED),
            ("Assumption", "assumptions", StatementClassification.AI_INFERRED),
            ("Open Question", "openQuestions", StatementClassification.UNKNOWN),
        ):
            for value in _unique(_strings(analysis.get(key))):
                matched = _matching_evidence(value, evidence)
                item_classification = StatementClassification.EVIDENCE if matched else classification
                statements.append(_statement(
                    category, value, item_classification, matched,
                    "Supported by engineering evidence." if matched else _why(category, value),
                    provider, model, prompt_version, generated_at,
                ))
        for value in capabilities:
            classification = StatementClassification.SOURCE if _supported(value, source_text) else StatementClassification.AI_INFERRED
            statements.append(_statement(
                "Capability", value, classification,
                ["source:requirement"], "Capability normalizes the source intent without adding behavior.",
                provider, model, prompt_version, generated_at,
            ))

        return {
            "schemaVersion": "hei-statement-governance-v1",
            "statements": statements,
            "governedValues": governed_values,
            "acceptedFunctionalRequirements": accepted_functional,
            "acceptedNonFunctionalRequirements": source_non_functional,
            "candidateNonFunctionalRequirements": candidate_non_functional,
            "suggestedEnhancements": suggested_enhancements,
            "unknownInformation": [item for item in statements if item["classification"] == StatementClassification.UNKNOWN.value],
            "diagnostics": {
                "acceptedFunctionalCount": len(accepted_functional),
                "suggestionCount": len(suggested_enhancements) + sum(bool(item.get("requiresConfirmation")) for item in candidate_non_functional),
                "provider": provider,
                "model": model,
                "promptVersion": prompt_version,
            },
        }

    @staticmethod
    def _classify_functional(
        value: str, source_text: str, evidence: list[dict[str, Any]],
    ) -> tuple[StatementClassification, list[str], str]:
        unsupported = _unsupported_pattern(value, source_text, evidence)
        if unsupported:
            return StatementClassification.AI_SUGGESTION, [], unsupported
        if _supported(value, source_text):
            return StatementClassification.SOURCE, ["source:requirement"], "Directly stated or faithfully paraphrased by the requirement source."
        matched = _matching_evidence(value, evidence)
        if matched:
            return StatementClassification.EVIDENCE, matched, "Verified by selected engineering evidence."
        return StatementClassification.AI_SUGGESTION, [], "The statement introduces behavior not supported by the source or selected evidence."

    @staticmethod
    def _govern_business_goal(value: str, source: str) -> str:
        if value and not _same_meaning(value, source) and not _looks_like_requirement(value):
            return value
        lowered = source.casefold()
        if "firmware" in lowered and "offline" in lowered:
            return "Reduce device downtime and maintenance disruption when firmware delivery cannot rely on network connectivity."
        if any(term in lowered for term in ("health", "fault", "failure", "alarm")):
            return "Reduce operational disruption by helping teams identify deteriorating conditions earlier."
        if any(term in lowered for term in ("dashboard", "monitor", "visibility")):
            return "Improve operational visibility so teams can recognize and respond to issues earlier."
        return "Improve the business outcome of the requested workflow while preserving the stated scope."

    @staticmethod
    def _govern_problem_statement(value: str, source: str) -> str:
        if value and not _same_meaning(value, source) and not _looks_like_requirement(value):
            return value
        lowered = source.casefold()
        if "firmware" in lowered and "offline" in lowered:
            return "Firmware maintenance is constrained when devices cannot rely on an active network connection."
        if any(term in lowered for term in ("health", "fault", "failure", "alarm")):
            return "Teams lack timely visibility into deteriorating conditions, delaying intervention before operational impact."
        return "The current process does not reliably provide the outcome described by the requirement."

    @staticmethod
    def _govern_business_value(value: str, source: str) -> str:
        if value and not _same_meaning(value, source) and value.casefold() not in {"requires clarification", "needs clarification"}:
            return value
        lowered = source.casefold()
        if "firmware" in lowered:
            return "Reduced maintenance interruption and more reliable firmware servicing in disconnected environments."
        if any(term in lowered for term in ("health", "fault", "failure", "alarm")):
            return "Earlier intervention, reduced downtime, and less manual investigation."
        if any(term in lowered for term in ("dashboard", "monitor", "visibility")):
            return "Faster operational decisions through clearer, centralized visibility."
        return "Less manual effort and a more reliable operational outcome."


def _statement(
    category: str, text: str, classification: StatementClassification,
    evidence: list[str], reason: str, provider: str, model: str,
    prompt_version: str, generated_at: str,
) -> dict[str, Any]:
    confidence = {
        StatementClassification.SOURCE: 1.0,
        StatementClassification.EVIDENCE: 0.9,
        StatementClassification.AI_INFERRED: 0.76,
        StatementClassification.AI_SUGGESTION: 0.55,
        StatementClassification.UNKNOWN: 0.25,
    }[classification]
    return {
        "id": f"statement_{uuid4().hex}", "category": category, "text": text,
        "classification": classification.value, "source": _source_label(classification),
        "provider": provider if classification in {StatementClassification.AI_INFERRED, StatementClassification.AI_SUGGESTION} else "",
        "model": model if classification in {StatementClassification.AI_INFERRED, StatementClassification.AI_SUGGESTION} else "",
        "promptVersion": prompt_version if classification in {StatementClassification.AI_INFERRED, StatementClassification.AI_SUGGESTION} else "",
        "confidence": confidence, "evidenceReferences": list(dict.fromkeys(evidence)),
        "generatedAt": generated_at,
        "approvedStatus": "PendingReview" if classification == StatementClassification.AI_SUGGESTION else "NotRequired",
        "why": reason,
    }


def _all_evidence(report: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for key in (
        "repositoryEvidence", "relevantDocumentation", "azureDevOpsEvidence",
        "engineeringMemoryEvidence", "projectIntelligenceEvidence", "knowledgeEvidence",
    ):
        values.extend(item for item in report.get(key) or [] if isinstance(item, dict))
    return values


def _matching_evidence(value: str, evidence: list[dict[str, Any]]) -> list[str]:
    return [
        _text(item.get("sourceReference")) for item in evidence
        if _text(item.get("sourceReference"))
        and _overlap(value, " ".join([_text(item.get("title")), _text(item.get("reason")), str(item.get("metadata") or "")])) >= 0.3
    ][:8]


def _unsupported_pattern(value: str, source: str, evidence: list[dict[str, Any]]) -> str:
    evidence_text = " ".join(
        " ".join([_text(item.get("title")), _text(item.get("reason")), str(item.get("metadata") or "")])
        for item in evidence
    )
    lowered = value.casefold()
    for pattern, reason in _SUGGESTION_PATTERNS.items():
        if pattern in lowered and pattern not in source.casefold() and pattern not in evidence_text.casefold():
            return reason
    return ""


def _supported(value: str, source: str) -> bool:
    normalized_value = _normalize(value)
    normalized_source = _normalize(source)
    return bool(normalized_value and (normalized_value in normalized_source or _overlap(value, source) >= 0.55))


def _overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    return len(left_tokens & right_tokens) / max(1, len(left_tokens))


def _same_meaning(left: str, right: str) -> bool:
    return _overlap(left, right) >= 0.75 and _overlap(right, left) >= 0.45


def _looks_like_requirement(value: str) -> bool:
    return bool(re.match(r"^(?:provide|allow|enable|implement|create|add|show|display|support|the system)", value.strip(), re.I))


def _infer_actor(source: str) -> str:
    lowered = source.casefold()
    if "firmware" in lowered:
        return "Maintenance Engineer"
    if any(term in lowered for term in ("health", "fault", "alarm", "operations", "dashboard", "monitor")):
        return "Operations User"
    if any(term in lowered for term in ("deploy", "pipeline", "code", "api")):
        return "Software Engineer"
    return "Business User"


def _why(category: str, value: str) -> str:
    if not value:
        return f"{category} cannot be determined from the current source or evidence."
    return {
        "Business Goal": "Interprets why the requested outcome matters without adding functionality.",
        "Problem Statement": "Describes the current limitation implied by the requirement.",
        "Business Value": "States the likely operational value of the requested outcome.",
        "Primary Actor": "Identifies the most likely user of the stated capability.",
        "Risk": "Potential delivery or operational risk inferred from the bounded requirement.",
        "Assumption": "Unverified interpretation retained explicitly as an assumption.",
        "Open Question": "Information cannot be determined from the source or selected evidence.",
    }.get(category, "Derived from the requirement intent.")


def _source_label(classification: StatementClassification) -> str:
    return {
        StatementClassification.SOURCE: "User Requirement",
        StatementClassification.EVIDENCE: "Engineering Evidence",
        StatementClassification.AI_INFERRED: "AI Reasoning",
        StatementClassification.AI_SUGGESTION: "AI Suggestion",
        StatementClassification.UNKNOWN: "Unknown",
    }[classification]


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _tokens(value: str) -> set[str]:
    ignored = {"the", "and", "for", "with", "from", "that", "this", "into", "must", "should", "system", "user", "users", "provide", "allow", "enable", "need"}
    return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 2 and token not in ignored}


def _strings(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item.get("text") if isinstance(item, dict) else item) for item in value if _text(item.get("text") if isinstance(item, dict) else item)]
    return [_text(value)] if _text(value) else []


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _text(value: Any) -> str:
    return str(value or "").strip()
