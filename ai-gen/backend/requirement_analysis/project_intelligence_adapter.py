"""Compatibility adapter for stabilized Project Intelligence requirement reasoning."""

from __future__ import annotations

import re
from typing import Any

from backend.refinement.provider import get_refiner_status


class ProjectIntelligenceRequirementAnalyzer:
    """Translate current Requirement models to the Project Intelligence facade."""

    def __init__(self, project_intelligence: Any) -> None:
        self._project_intelligence = project_intelligence

    def analyze(
        self, requirement: dict[str, Any], engineering_context: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            result = self._project_intelligence.analyze_requirement_intelligence(
                requirement,
                engineering_context,
                options={"force_provider": "azure_phi", "allow_fallback": True},
            )
        except TypeError:
            # Compatibility for older facade implementations and test doubles.
            result = self._project_intelligence.analyze_requirement_intelligence(
                requirement, engineering_context,
            )
        return self._reasoning_result(result, "requirement-analysis-project-intelligence-v1")

    def refine(
        self, requirement: dict[str, Any], engineering_context: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            result = self._project_intelligence.refine_requirement_intelligence(
                requirement,
                engineering_context,
                options={"force_provider": "azure_phi", "allow_fallback": True},
            )
        except TypeError:
            # Compatibility for older facade implementations and test doubles.
            result = self._project_intelligence.refine_requirement_intelligence(
                requirement, engineering_context,
            )
        return self._reasoning_result(result, "requirement-refinement-project-intelligence-v2")

    @staticmethod
    def is_provider_available(_preference: str = "Auto") -> bool:
        status = get_refiner_status()
        return bool(status.get("enabled"))

    def generate_acceptance_criteria(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
        engineering_context: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            result = self._project_intelligence.generate_requirement_acceptance_criteria(
                requirement,
                engineering_context,
                options={"force_provider": "azure_phi"},
            )
        except TypeError:
            # Compatibility for older facade implementations and test doubles.
            result = self._project_intelligence.generate_requirement_acceptance_criteria(
                requirement, engineering_context,
            )
        metadata = dict(result.get("metadata") or {})
        criteria = self._validated_criteria(
            result.get("acceptanceCriteria") or [], analysis, engineering_context,
        )
        result = {**result, "used": bool(result.get("used")) and bool(criteria)}
        reasoning = self._reasoning_result(
            result, "requirement-acceptance-project-intelligence-v1",
        )
        for criterion in criteria:
            criterion["model"] = reasoning["model"]
            criterion["promptVersion"] = reasoning["promptVersion"]
            criterion["evidenceMapping"] = list(criterion.get("evidence") or [])
        reasoning["recommendation"] = {"acceptanceCriteria": criteria}
        reasoning["diagnostics"].update({
            "qualityScore": metadata.get("acceptance_quality_score"),
            "qualityGate": metadata.get("quality_gate"),
            "rejectedCriteria": list(metadata.get("rejected_acceptance_criteria") or []),
        })
        return reasoning

    @staticmethod
    def _reasoning_result(result: dict[str, Any], prompt_version: str) -> dict[str, Any]:
        metadata = dict(result.get("metadata") or {})
        used = bool(result.get("used"))
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        reason = str(metadata.get("fallback_reason") or "").strip()
        confidence = _confidence(analysis.get("confidence"), 82 if used else 35)
        return {
            "status": "Completed" if used else "Degraded",
            "reasoningMode": "AI" if used else "Deterministic",
            "provider": "Project Intelligence" if used else "Deterministic",
            "model": str(
                metadata.get("provider_deployment")
                or metadata.get("model")
                or metadata.get("deployment")
                or ""
            ),
            "promptVersion": prompt_version,
            "recommendation": analysis,
            "reasoning": _strings(analysis.get("reasoning") or analysis.get("engineeringInsights")),
            "alternatives": _strings(analysis.get("alternatives")),
            "warnings": [reason] if reason else [],
            "evidence": list(analysis.get("evidence") or []),
            "confidence": {"overall": confidence, "level": _confidence_level(confidence)},
            "telemetry": {
                "promptTokens": metadata.get("phi_prompt_tokens") or metadata.get("prompt_tokens"),
                "completionTokens": metadata.get("phi_completion_tokens") or metadata.get("completion_tokens"),
                "latencyMs": metadata.get("phi_latency_ms") or metadata.get("latency_ms"),
            },
            "diagnostics": {
                **metadata,
                "engine": "ProjectIntelligenceRequirementAdapterV1",
                "projectIntelligencePrimary": True,
                "degraded": not used,
                "retryAvailable": not used,
            },
        }

    @staticmethod
    def _validated_criteria(
        raw: list[Any], analysis: dict[str, Any], engineering_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        functional = _strings(analysis.get("functionalRequirements"))
        evidence_text = " ".join([
            *functional,
            *_strings(analysis.get("businessRules")),
            *_strings(analysis.get("constraints")),
            *_strings(analysis.get("planningRequirement")),
        ]).casefold()
        source_versions = engineering_context.get("sourceVersions") if isinstance(engineering_context.get("sourceVersions"), dict) else {}
        criteria: list[dict[str, Any]] = []
        seen_text: set[str] = set()
        seen_behaviors: set[tuple[str, str]] = set()
        seen_titles: set[str] = set()
        for index, candidate in enumerate(raw):
            value = dict(candidate) if isinstance(candidate, dict) else {"text": str(candidate)}
            text = str(value.get("text") or "").strip()
            normalized = re.sub(r"\s+", " ", text).casefold()
            behavior = _criterion_behavior(text)
            if (
                not text
                or normalized in seen_text
                or behavior in seen_behaviors
                or not _is_testable(text)
                or _is_circular(text)
            ):
                continue
            if _unsupported_without_evidence(text, evidence_text):
                continue
            mapped = str(value.get("mappedFunctionalRequirement") or "").strip()
            if mapped not in functional:
                mapped = functional[min(index, len(functional) - 1)] if functional else ""
            if not mapped:
                continue
            confidence = _confidence(value.get("confidence"), 80) / 100
            evidence = value.get("evidence") if isinstance(value.get("evidence"), list) else []
            if not evidence:
                evidence = [{
                    "requirementSentence": mapped,
                    "matchedPhrase": mapped,
                    "confidence": confidence,
                    "source": "Engineering Context",
                }]
            title = _criterion_title(value, text)
            if title.casefold() in seen_titles:
                title = _criterion_title(value, text, include_trigger=True)
            if title.casefold() in seen_titles:
                continue
            criteria.append({
                **value,
                "title": title,
                "text": text,
                "mappedFunctionalRequirement": mapped,
                "evidence": evidence,
                "confidence": confidence,
                "confidenceBasis": value.get("confidenceBasis") or "Mapped to supplied functional evidence.",
                "origin": "Project Intelligence Generated",
                "provider": "Project Intelligence",
                "contextVersion": engineering_context.get("contextVersion"),
                "knowledgeVersion": source_versions.get("projectKnowledgeVersion"),
                "repositoryRevision": (
                    (source_versions.get("repositoryMarkdown") or {}).get("repositoryRevision")
                    if isinstance(source_versions.get("repositoryMarkdown"), dict)
                    else None
                ) or source_versions.get("repositorySnapshotVersion"),
            })
            seen_text.add(normalized)
            seen_behaviors.add(behavior)
            seen_titles.add(title.casefold())
        return criteria


def _criterion_behavior(text: str) -> tuple[str, str]:
    """Identify the behavior under test independently of a shared precondition."""
    compact = re.sub(r"\s+", " ", text).strip()
    when = re.search(r"\bwhen\b\s+(.+?)(?=\bthen\b|$)", compact, re.I)
    then = re.search(r"\bthen\b\s+(.+)$", compact, re.I)
    return (_normalize_clause(when.group(1) if when else ""), _normalize_clause(then.group(1) if then else compact))


def _criterion_title(value: dict[str, Any], text: str, *, include_trigger: bool = False) -> str:
    supplied = str(value.get("title") or "").strip()
    if supplied and not re.match(r"^(?:given|when|then)\b", supplied, re.I):
        return _trim_title(supplied)
    scenario = re.search(r"^\s*Scenario:\s*(.+)$", text, re.I | re.M)
    if scenario:
        return _trim_title(scenario.group(1))
    compact = re.sub(r"\s+", " ", text).strip()
    then = re.search(r"\bthen\b\s+(.+)$", compact, re.I)
    when = re.search(r"\bwhen\b\s+(.+?)(?=\bthen\b|$)", compact, re.I)
    outcome = _display_clause(then.group(1) if then else compact)
    if include_trigger and when:
        outcome = f"{_display_clause(when.group(1))}: {outcome}"
    return _trim_title(outcome or "Acceptance Criterion")


def _normalize_clause(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _display_clause(value: str) -> str:
    text = value.strip().strip(". ")
    text = re.sub(r"^(?:the|a|an)\s+", "", text, flags=re.I)
    text = re.sub(r"\bshould\s+be\b", "is", text, flags=re.I)
    text = re.sub(r"\bshould\b", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _trim_title(value: str) -> str:
    words = value.split()
    return " ".join(words[:14]).strip(" .:").title() or "Acceptance Criterion"


def _unsupported_without_evidence(text: str, evidence: str) -> bool:
    unsupported = (
        "authentication", "authorization", "permission", "role-based", "login",
        "crud", "audit", "session", "input validation",
    )
    lowered = text.casefold()
    return any(term in lowered and term not in evidence for term in unsupported)


def _is_testable(text: str) -> bool:
    lowered = text.casefold()
    return (
        all(token in lowered for token in ("given", "when", "then"))
        or any(token in lowered for token in (" can ", " displays ", " returns ", " is visible", " appears "))
    )


def _is_circular(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", text.casefold())
    if "observable result" in lowered:
        return True
    when = re.search(r"\bwhen\s+(?:the user\s+)?([a-z]+)", lowered)
    if not when:
        return False
    verb = when.group(1).removesuffix("es").removesuffix("s")
    return bool(re.search(rf"\bthen\b.*\bcan be\s+{re.escape(verb)}(?:ed|d)?\b", lowered))


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _confidence(value: Any, default: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number <= 1:
        number *= 100
    return max(0, min(100, round(number)))


def _confidence_level(value: int) -> str:
    if value >= 80:
        return "High"
    if value >= 55:
        return "Medium"
    return "Low"
