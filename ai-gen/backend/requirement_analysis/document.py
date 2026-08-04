"""Canonical Requirement Analysis V2 document assembly and validation."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import RequirementAnalysisDocument


class RequirementAnalysisDocumentBuilder:
    """Combines AI interpretation with traceable Engineering Discovery facts."""

    def build(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
        engineering_context: dict[str, Any],
        discovery: dict[str, Any],
        reasoning: dict[str, Any],
    ) -> dict[str, Any]:
        report = dict(discovery.get("report") or {})
        recommendation = dict(reasoning.get("recommendation") or {})
        refinement = dict(analysis.get("requirementRefinement") or {})
        intent = dict(analysis.get("requirementIntent") or {})
        governance = dict(analysis.get("statementGovernance") or {})
        governed = dict(governance.get("governedValues") or {})

        # Governance has already removed unsupported provider suggestions. Never
        # re-merge the raw provider payload into the canonical planning input.
        functional = _unique(_strings(analysis.get("functionalRequirements")))
        business_goal = _first(
            governed.get("businessGoal"),
            recommendation.get("businessGoal"),
            refinement.get("businessGoal"),
            refinement.get("businessObjective"),
            intent.get("businessGoal"),
            *(_strings(analysis.get("businessGoals"))),
        )
        if functional and _same_meaning(business_goal, functional[0]):
            business_goal = _first(
                recommendation.get("businessValue"),
                refinement.get("expectedOutcome"),
            )

        actors = _unique([
            _text(governed.get("primaryActor")),
            _text(recommendation.get("primaryActor")),
            _text(refinement.get("primaryActor")),
            _text(intent.get("primaryActor")),
            *_strings(analysis.get("actors")),
        ])
        secondary = _unique(
            _strings(governed.get("secondaryActors"))
            + _strings(recommendation.get("secondaryActors"))
            + _strings(refinement.get("secondaryActors"))
            + _strings(intent.get("secondaryActors"))
            + actors[1:]
        )
        primary_actor = actors[0] if actors else ""
        capabilities = _unique(
            _strings(governed.get("capabilities"))
            + _strings(recommendation.get("capabilities"))
            + _strings(refinement.get("coreCapabilities"))
            + _strings(intent.get("capabilities"))
        )

        repository_findings = _evidence(report.get("repositoryEvidence"))
        markdown_findings = _evidence(report.get("relevantDocumentation"))
        azure_devops_findings = _evidence(report.get("azureDevOpsEvidence"))
        reusable_components = _evidence(report.get("reusableComponents"))
        all_evidence = _unique_evidence([
            *repository_findings,
            *markdown_findings,
            *azure_devops_findings,
            *reusable_components,
            *_evidence(report.get("architectureEvidence")),
            *_evidence(report.get("engineeringMemoryEvidence")),
            *_evidence(report.get("projectIntelligenceEvidence")),
            *_evidence(report.get("knowledgeEvidence")),
        ])
        evidence_references = [item["sourceReference"] for item in all_evidence]
        source_reference = ["source:requirement"]

        business_rules = self._evidence_required_values(
            recommendation.get("businessRules"), analysis.get("businessRules"),
            analysis, "businessRules", evidence_references,
        )
        constraints = self._evidence_required_values(
            recommendation.get("constraints"), analysis.get("constraints"),
            analysis, "constraints", evidence_references,
        )
        dependencies = self._evidence_required_values(
            recommendation.get("dependencies"), analysis.get("dependencies"),
            analysis, "dependencies", evidence_references,
        )

        affected = self._affected(report)
        risks = _unique(
            _strings(recommendation.get("risks"))
            + _strings(analysis.get("risks"))
            + _strings(reasoning.get("risks"))
        )
        assumptions = _unique(
            _strings(recommendation.get("assumptions"))
            + _strings(analysis.get("assumptions"))
        )
        questions = self._unresolved_questions(
            _unique(
                _strings(recommendation.get("openQuestions"))
                + _strings(analysis.get("openQuestions"))
                + [str(item.get("reason") or "") for item in report.get("unknowns") or []]
            ),
            all_evidence,
        )
        insights = _unique(
            _strings(recommendation.get("engineeringInsights"))
            + _strings((analysis.get("evidenceSynthesis") or {}).get("engineeringInsights"))
            + [str(item.get("summary") or "") for item in report.get("whatIFound") or [] if int(item.get("count") or 0) > 0]
        )

        readiness = self._readiness(analysis, report, business_goal, functional, primary_actor, capabilities)
        confidence = self._confidence(analysis, report, readiness)
        section_sources = {
            "executiveSummary": _source("AI Reasoning" if recommendation.get("executiveSummary") else "Requirement Analysis", reasoning, source_reference),
            "businessGoal": _source(_origin(analysis, "businessGoals"), reasoning, source_reference),
            "problemStatement": _source("AI Reasoning" if recommendation.get("problemStatement") else "Requirement Refinement", reasoning, source_reference),
            "actors": _source(_origin(analysis, "actors"), reasoning, source_reference),
            "businessValue": _source("AI Reasoning" if recommendation.get("businessValue") else "Requirement Refinement", reasoning, source_reference),
            "capabilities": _source("AI Interpretation", reasoning, source_reference),
            "functionalRequirements": _source(_origin(analysis, "functionalRequirements"), reasoning, source_reference),
            "candidateNonFunctionalRequirements": _source(_origin(analysis, "nonFunctionalRequirements"), reasoning, source_reference),
            "businessRules": _source(_origin(analysis, "businessRules"), reasoning, evidence_references or source_reference),
            "constraints": _source(_origin(analysis, "constraints"), reasoning, evidence_references or source_reference),
            "dependencies": _source(_origin(analysis, "dependencies"), reasoning, evidence_references or source_reference),
            "repositoryImpact": _source("Engineering Discovery", reasoning, [item["sourceReference"] for item in repository_findings]),
            "risks": _source("AI Inferred", reasoning, evidence_references or source_reference),
            "assumptions": _source("AI Inferred", reasoning, source_reference),
            "openQuestions": _source("Evidence Gap", reasoning, evidence_references),
            "engineeringInsights": _source("Engineering Discovery", reasoning, evidence_references),
        }

        document_values = {
            "document_id": f"requirement_analysis_document_{uuid4().hex}",
            "requirement_id": _text(requirement.get("requirementId")),
            "context_version": _text(requirement.get("contextVersion")) or "1.0",
            "title": _text(requirement.get("title")) or "Engineering Requirement",
            "executive_summary": _first(
                recommendation.get("executiveSummary"),
                refinement.get("executiveSummary"),
                analysis.get("requirementSummary"),
            ),
            "business_goal": business_goal,
            "problem_statement": _first(
                governed.get("problemStatement"),
                recommendation.get("problemStatement"),
                refinement.get("problemStatement"),
                f"The requirement does not yet define a distinct problem statement for {primary_actor}." if primary_actor else "A distinct problem statement was not provided or inferred.",
            ),
            "primary_actor": primary_actor,
            "secondary_actors": secondary,
            "business_value": _first(
                governed.get("businessValue"),
                recommendation.get("businessValue"),
                refinement.get("expectedOutcome"),
                refinement.get("businessGoal"),
            ),
            "capabilities": capabilities,
            "functional_requirements": functional,
            "candidate_non_functional_requirements": _unique(
                _strings(analysis.get("nonFunctionalRequirements"))
                + _strings(analysis.get("candidateNonFunctionalRequirements"))
            ),
            "acceptance_criteria": _strings(analysis.get("acceptanceCriteria")),
            "business_rules": business_rules,
            "constraints": constraints,
            "dependencies": dependencies,
            "affected_modules": affected["modules"],
            "affected_services": affected["services"],
            "affected_apis": affected["apis"],
            "affected_screens": affected["screens"],
            "repository_findings": repository_findings,
            "markdown_findings": markdown_findings,
            "azure_devops_findings": azure_devops_findings,
            "reusable_components": reusable_components,
            "risks": risks,
            "assumptions": assumptions,
            "open_questions": questions,
            "engineering_insights": insights,
            "statement_governance": list(governance.get("statements") or []),
            "suggested_enhancements": list(governance.get("suggestedEnhancements") or []),
            "planning_readiness": readiness,
            "confidence": confidence,
            "evidence": all_evidence,
            "section_sources": section_sources,
            "validation": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        document_values["validation"] = self._validate(document_values)
        return RequirementAnalysisDocument(**document_values).to_dict()

    @staticmethod
    def _evidence_required_values(
        reasoned: Any,
        existing: Any,
        analysis: dict[str, Any],
        field_name: str,
        evidence_references: list[str],
    ) -> list[str]:
        origin = _origin(analysis, field_name)
        source_values = _strings(existing)
        if source_values and origin in {"Source", "Imported", "User Edited"}:
            return source_values
        return _strings(reasoned) if evidence_references else []

    @staticmethod
    def _affected(report: dict[str, Any]) -> dict[str, list[str]]:
        output = {"modules": [], "services": [], "apis": [], "screens": []}
        mapping = {"module": "modules", "service": "services", "api": "apis", "screen": "screens"}
        for item in report.get("repositoryEvidence") or []:
            if not isinstance(item, dict):
                continue
            bucket = mapping.get(_text(item.get("evidenceType")).casefold())
            if bucket:
                output[bucket].append(_text(item.get("title")))
        return {key: _unique(values) for key, values in output.items()}

    @staticmethod
    def _unresolved_questions(questions: list[str], evidence: list[dict[str, Any]]) -> list[str]:
        evidence_text = " ".join(
            f"{item.get('title', '')} {item.get('reason', '')}" for item in evidence
        )
        evidence_tokens = _tokens(evidence_text)
        result = []
        for question in questions:
            question_tokens = _tokens(question)
            overlap = len(question_tokens & evidence_tokens) / max(1, len(question_tokens))
            if overlap < 0.7:
                result.append(question)
        return _unique(result)

    @staticmethod
    def _readiness(
        analysis: dict[str, Any],
        report: dict[str, Any],
        business_goal: str,
        functional: list[str],
        primary_actor: str,
        capabilities: list[str],
    ) -> dict[str, Any]:
        current = dict(analysis.get("planningReadiness") or {})
        score = int(current.get("score") or analysis.get("requirementQualityScore") or 0)
        dimensions = {
            "businessClarity": 100 if business_goal else 35,
            "functionalClarity": min(100, 35 + len(functional) * 20),
            "actorClarity": 100 if primary_actor else 40,
            "capabilityClarity": min(100, 35 + len(capabilities) * 20),
            "engineeringEvidence": int((report.get("confidence") or {}).get("score") or 0),
        }
        status = str(current.get("status") or "NeedsUserInput")
        blockers = _strings(current.get("blockers"))
        warnings = _strings(current.get("warnings"))
        if (not business_goal or not functional) and status != "Blocked":
            status = "NeedsUserInput"
            if not business_goal:
                warnings.append("A distinct Business Goal requires user confirmation.")
            if not functional:
                blockers.append("At least one Functional Requirement is required for Planning.")
        elif (not primary_actor or not capabilities) and status == "Ready":
            status = "ReadyWithRecommendations"
            if not primary_actor:
                warnings.append("Confirm the primary actor before Planning approval.")
            if not capabilities:
                warnings.append("Confirm at least one capability before Planning approval.")
        explanation = (
            f"{len(functional)} governed functional requirement(s) and {len(capabilities)} capability signal(s) "
            f"are available. {(report.get('confidence') or {}).get('evidenceCount') or 0} engineering evidence "
            f"item(s) were selected. The score is supporting context, not the decision itself."
        )
        strengths = []
        attention = []
        if business_goal:
            strengths.append("A distinct business outcome is defined.")
        if functional:
            strengths.append(f"{len(functional)} governed functional requirement(s) are ready for planning.")
        if primary_actor:
            strengths.append(f"Primary actor identified as {primary_actor}.")
        if int((report.get("confidence") or {}).get("evidenceCount") or 0):
            strengths.append("Engineering findings include traceable source references.")
        attention.extend(_unique([*blockers, *warnings]))
        if analysis.get("suggestedEnhancements"):
            attention.append("AI suggestions remain outside the planning scope until explicitly approved.")
        return {
            **current,
            "status": status,
            "score": score,
            "readyForPlanning": status in {"Ready", "ReadyWithRecommendations"},
            "blockers": _unique(blockers),
            "warnings": _unique(warnings),
            "strengths": _unique(strengths),
            "needsAttention": _unique(attention),
            "explanation": explanation,
            "dimensions": dimensions,
            "evidenceStatus": report.get("status") or "DiscoveryPending",
        }

    @staticmethod
    def _confidence(
        analysis: dict[str, Any], report: dict[str, Any], readiness: dict[str, Any],
    ) -> dict[str, Any]:
        analysis_score = round(float(analysis.get("confidence") or 0) * 100)
        discovery_score = int((report.get("confidence") or {}).get("score") or 0)
        readiness_score = int(readiness.get("score") or 0)
        score = round(analysis_score * 0.45 + discovery_score * 0.3 + readiness_score * 0.25)
        return {
            "score": score,
            "level": "High" if score >= 80 else "Medium" if score >= 55 else "Low",
            "reason": (
                f"Weighted from requirement interpretation ({analysis_score}%), engineering discovery "
                f"({discovery_score}%), and planning readiness ({readiness_score}%)."
            ),
        }

    @staticmethod
    def _validate(value: dict[str, Any]) -> dict[str, Any]:
        functional = value["functional_requirements"]
        business_goal_distinct = not functional or not _same_meaning(value["business_goal"], functional[0])
        repository_evidence_valid = all(
            item.get("sourceReference") and item.get("reason")
            for item in value["repository_findings"]
        )
        checks = {
            "businessGoalDistinct": business_goal_distinct,
            "actorIdentified": bool(value["primary_actor"]),
            "capabilitiesPresent": bool(value["capabilities"]),
            "repositoryEvidenceValid": repository_evidence_valid,
            "planningReadinessExplained": bool(value["planning_readiness"].get("explanation")),
            "suggestionsExcludedFromFunctionalRequirements": not any(
                item.get("classification") == "AI_SUGGESTION"
                and item.get("category") == "Functional Requirement"
                and item.get("text") in functional
                for item in value.get("statement_governance") or []
            ),
        }
        warnings = []
        if not business_goal_distinct:
            warnings.append("Business Goal duplicates a Functional Requirement and requires review.")
        if not checks["actorIdentified"]:
            warnings.append("No primary actor could be identified from the requirement or evidence.")
        if not checks["capabilitiesPresent"]:
            warnings.append("No capability could be identified without expanding the requirement.")
        if not repository_evidence_valid:
            warnings.append("One or more repository findings lack traceable evidence.")
        return {"valid": all(checks.values()), "checks": checks, "warnings": warnings}


def _source(
    origin: str,
    reasoning: dict[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    return {
        "origin": origin or "Not Available",
        "evidenceReferences": list(dict.fromkeys(evidence_references)),
        "provider": reasoning.get("provider") if "AI" in (origin or "") else "",
        "reasoningMode": reasoning.get("reasoningMode") if "AI" in (origin or "") else "",
    }


def _origin(analysis: dict[str, Any], key: str) -> str:
    return _text((analysis.get("fieldOrigins") or {}).get(key)) or "Requirement Analysis"


def _evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        dict(item)
        for item in value
        if isinstance(item, dict)
        and _text(item.get("sourceReference"))
        and _text(item.get("reason"))
    ]


def _unique_evidence(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        reference = _text(item.get("sourceReference"))
        if reference and reference not in seen:
            seen.add(reference)
            output.append(item)
    return output


def _first(*values: Any) -> str:
    return next((_text(value) for value in values if _text(value)), "")


def _strings(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item.get("text") if isinstance(item, dict) else item) for item in value if _text(item.get("text") if isinstance(item, dict) else item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tokens(value: Any) -> set[str]:
    ignored = {"and", "the", "for", "with", "from", "that", "this", "into", "user", "users"}
    return {
        token for token in re.findall(r"[a-z0-9]+", _text(value).casefold())
        if len(token) > 2 and token not in ignored
    }


def _same_meaning(left: str, right: str) -> bool:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens)) >= 0.82


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
