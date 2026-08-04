"""Persistence and orchestration for Requirement Analysis."""

from __future__ import annotations

import re
import os
from typing import Any
from datetime import datetime, timezone
from uuid import uuid4

from backend.platform.shared import JsonMapStore
from backend.engineering_intelligence import EngineeringIntelligenceService
from backend.requirement_intake.ingestion import RequirementIngestionService

from .acceptance_criteria import IntelligentAcceptanceCriteriaEngine
from .document import RequirementAnalysisDocumentBuilder
from .engine import RequirementAnalysisEngine
from .governance import RequirementGovernanceEngine
from .models import RequirementFinding


class RequirementAnalysisService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        requirement_ingestion: RequirementIngestionService,
        engine: RequirementAnalysisEngine | None = None,
        acceptance_engine: IntelligentAcceptanceCriteriaEngine | None = None,
        document_builder: RequirementAnalysisDocumentBuilder | None = None,
        governance_engine: RequirementGovernanceEngine | None = None,
        repository_detector: Any | None = None,
        engineering_intelligence: Any | None = None,
        reasoning_engine: Any | None = None,
        project_intelligence_analyzer: Any | None = None,
        refinement_service: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.requirement_ingestion = requirement_ingestion
        self.engine = engine or RequirementAnalysisEngine()
        self.acceptance_engine = acceptance_engine or IntelligentAcceptanceCriteriaEngine()
        self.document_builder = document_builder or RequirementAnalysisDocumentBuilder()
        self.governance_engine = governance_engine or RequirementGovernanceEngine()
        self.repository_detector = repository_detector
        self.engineering_intelligence = engineering_intelligence or EngineeringIntelligenceService(
            repository_detector=repository_detector,
        )
        self.reasoning_engine = reasoning_engine
        self.project_intelligence_analyzer = project_intelligence_analyzer
        self.refinement_service = refinement_service
        self.platform = platform

    def analyze(self, requirement_id: str, *, force: bool = False) -> dict[str, Any]:
        requirement = self.requirement_ingestion.get(requirement_id)
        if not requirement:
            raise ValueError("Requirement context was not found. Ingest the source before analysis.")
        refinement: dict[str, Any] = {}
        if self.refinement_service:
            requirement, refinement = self.refinement_service.canonical_requirement(requirement_id)
        existing = self.get(requirement_id)
        if existing and not force and self._versions_current(existing) and existing.get("contentHash") == requirement.get("contentHash") and existing.get("contextVersion") == requirement.get("contextVersion") and existing.get("refinementVersion") == refinement.get("version") and existing.get("refinementStatus") == refinement.get("status"):
            return existing
        result = self.engine.analyze(requirement).to_dict()
        if refinement:
            intent = self._refinement_intent(refinement, result)
            intent_reasoning = self._refinement_reasoning(refinement)
            result["requirementRefinement"] = refinement
            result["refinementVersion"] = refinement.get("version")
            result["refinementStatus"] = refinement.get("status")
        else:
            intent_reasoning = self._reason_about_intent(requirement, result)
            intent = self._requirement_intent(intent_reasoning, result)
        result["requirementIntent"] = intent
        result["aiUnderstanding"] = self._reasoning_projection(intent_reasoning)
        self._apply_intent(result, intent)
        if self.engineering_intelligence:
            suggestion = self.engineering_intelligence.recommend_repository(requirement, result)
            result["repositorySuggestion"] = suggestion
            selected = suggestion.get("suggestedRepository") or {}
            if selected:
                result["reviewContext"]["repository"] = {
                    "id": selected.get("repositoryId", ""),
                    "name": selected.get("name", ""),
                    "status": "Suggested" if suggestion.get("source") != "ManualOverride" else "Manually Selected",
                }
                memory_count = int(suggestion.get("signals", {}).get("engineeringMemoryMatches") or 0)
                result["reviewContext"]["engineeringMemory"] = {
                    "status": f"{memory_count} relevant item(s)" if memory_count else "No relevant approved memory",
                    "message": "Engineering Memory supports repository selection but does not override current repository facts.",
                }
                matched_modules = selected.get("matchedModules") or []
                result["reviewContext"]["repositoryReuse"] = {
                    "status": f"{len(matched_modules)} matching module(s)" if matched_modules else "Repository metadata match",
                    "message": suggestion.get("reason") or "Repository reuse will be validated during Planning.",
                }
        engineering_context = self._build_engineering_context(requirement, result)
        result["engineeringContext"] = self._acceptance_context(engineering_context)
        if self.project_intelligence_analyzer:
            project_reasoning = self.project_intelligence_analyzer.analyze(requirement, engineering_context)
            if self._project_intelligence_shadow_mode():
                synthesis_reasoning = self._reason_about_requirement(requirement, result, engineering_context)
                synthesis_reasoning.setdefault("diagnostics", {})["projectIntelligenceShadow"] = project_reasoning
            else:
                synthesis_reasoning = project_reasoning
        else:
            synthesis_reasoning = self._reason_about_requirement(requirement, result, engineering_context)
        self._apply_evidence_synthesis(result, synthesis_reasoning)
        discovery = self._engineering_discovery(engineering_context)
        result["engineeringDiscovery"] = discovery
        governance = self.governance_engine.govern(
            requirement, result, discovery, synthesis_reasoning,
        )
        result["statementGovernance"] = governance
        self._apply_statement_governance(result, governance)
        result.update(self.acceptance_engine.understand(result, requirement))
        result["aiAnalysis"] = self._reasoning_projection(synthesis_reasoning)
        result["analysisDocument"] = self.document_builder.build(
            requirement, result, engineering_context, discovery, synthesis_reasoning,
        )
        result["analysisLineage"] = self._analysis_lineage(
            requirement, intent_reasoning, synthesis_reasoning, engineering_context,
        )
        result["analysisMode"] = (
            "AI"
            if any(
                item.get("reasoningMode") == "AI"
                for item in (intent_reasoning, synthesis_reasoning)
            )
            else "Deterministic"
        )
        values = self.store.read()
        values[requirement_id] = result
        self.store.write(values)
        self._publish(result, requirement)
        return result

    @staticmethod
    def _refinement_intent(refinement: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        source = dict(refinement.get("requirementIntent") or {})
        return _normalize_intent({
            "intentSummary": refinement.get("requirementSummary"),
            "businessGoal": source.get("businessGoal") or refinement.get("businessObjective"),
            "functionalIntent": source.get("functionalIntent") or [refinement.get("userIntent")],
            "entities": source.get("entities") or [],
            "primaryActor": refinement.get("primaryActor"),
            "actions": source.get("actions") or [],
            "concepts": source.get("concepts") or [],
            "searchKeywords": source.get("keywords") or [],
            "possibleRepositoryTerms": source.get("repositoryHints") or [],
            "possibleAzureDevOpsSearchTerms": source.get("azureDevOpsHints") or [],
            "possibleMarkdownSearchTerms": source.get("markdownHints") or [],
            "clarificationCandidates": source.get("clarificationCandidates") or refinement.get("clarificationCandidates") or [],
            "confidence": source.get("confidence") or refinement.get("confidence") or analysis.get("confidence"),
        })

    @staticmethod
    def _refinement_reasoning(refinement: dict[str, Any]) -> dict[str, Any]:
        provider = str(refinement.get("provider") or "Deterministic")
        mode = "AI" if provider != "Deterministic" else "Deterministic"
        return {
            "status": "Completed" if mode == "AI" else "Fallback",
            "reasoningMode": mode,
            "provider": provider,
            "model": str(refinement.get("model") or ""),
            "promptVersion": str(refinement.get("promptVersion") or ""),
            "recommendation": {"requirementIntent": refinement.get("requirementIntent") or {}},
            "insights": list(refinement.get("reasoning") or []),
            "alternatives": [],
            "warnings": list(refinement.get("warnings") or []),
            "confidence": {"overall": round(float(refinement.get("confidence") or 0) * 100)},
            "evidence": [{"referenceId": "source:requirement"}],
            "telemetry": {},
            "diagnostics": {"refinementId": refinement.get("refinementId"), "refinementVersion": refinement.get("version")},
        }

    def get(self, requirement_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(requirement_id)
        if not isinstance(value, dict):
            return None
        analysis = dict(value)
        state = analysis.get("acceptanceCriteriaState") or {}
        if (
            analysis.get("acceptanceCriteriaSuggestions")
            and analysis.get("missingAcceptanceCriteria")
            and state.get("state") == "AISuggested"
        ):
            requirement = self.requirement_ingestion.get(requirement_id)
            if requirement:
                self._refresh_acceptance_projection(analysis, requirement)
                self._save(requirement_id, analysis)
        return analysis

    def approve(self, requirement_id: str, actor: str) -> dict[str, Any]:
        analysis = self.get(requirement_id)
        requirement = self.requirement_ingestion.get(requirement_id)
        if not analysis or not requirement:
            raise ValueError("Requirement analysis was not found. Analyze the requirement before approval.")
        if analysis.get("contentHash") != requirement.get("contentHash") or analysis.get("contextVersion") != requirement.get("contextVersion"):
            raise ValueError("Requirement analysis is stale. Re-analyze the current requirement before approval.")
        if analysis.get("planningReadiness", {}).get("status") == "Blocked":
            raise ValueError("Blocked requirement analysis cannot be approved. Resolve the blocking findings first.")
        acceptance_state = analysis.get("acceptanceCriteriaState") or {}
        if acceptance_state.get("state") == "AISuggested" and acceptance_state.get("status") == "PendingReview":
            raise ValueError(
                "Review the generated Acceptance Criteria. Approve, edit, or discard them before Planning."
            )
        selected = (analysis.get("repositorySuggestion") or {}).get("suggestedRepository") or {}
        current_repository_id = str(requirement.get("metadata", {}).get("repositoryId") or "")
        selected_repository_id = str(selected.get("repositoryId") or "")
        if selected_repository_id and selected_repository_id != current_repository_id:
            reviewed_acceptance = {
                "acceptanceCriteria": list(analysis.get("acceptanceCriteria") or []),
                "acceptanceCriteriaRecords": list(analysis.get("acceptanceCriteriaRecords") or []),
                "acceptanceCriteriaSuggestions": list(analysis.get("acceptanceCriteriaSuggestions") or []),
                "acceptanceCriteriaState": dict(analysis.get("acceptanceCriteriaState") or {}),
                "acceptanceCriteriaOrigin": (analysis.get("fieldOrigins") or {}).get("acceptanceCriteria"),
            }
            self.requirement_ingestion.update_repository(
                requirement_id,
                repository_id=selected_repository_id,
                repository_name=str(selected.get("name") or ""),
                actor=actor or "HEI User",
            )
            analysis = self.analyze(requirement_id, force=True)
            requirement = self.requirement_ingestion.get(requirement_id) or requirement
            self._restore_reviewed_acceptance(analysis, reviewed_acceptance, requirement)
        analysis.update({
            "reviewStatus": "Approved",
            "approvedBy": actor or "HEI User",
            "approvedAt": datetime.now(timezone.utc).isoformat(),
            "approvedContentHash": requirement.get("contentHash"),
            "approvedContextVersion": requirement.get("contextVersion"),
        })
        self._save(requirement_id, analysis)
        self._publish_review("RequirementAnalysisApproved", analysis, requirement)
        return analysis

    def cancel(self, requirement_id: str, actor: str) -> dict[str, Any]:
        analysis = self.get(requirement_id)
        requirement = self.requirement_ingestion.get(requirement_id)
        if not analysis or not requirement:
            raise ValueError("Requirement analysis was not found.")
        analysis.update({
            "reviewStatus": "Cancelled", "approvedBy": "", "approvedAt": "",
            "approvedContentHash": "", "approvedContextVersion": "", "cancelledBy": actor or "HEI User",
        })
        self._save(requirement_id, analysis)
        self._publish_review("RequirementAnalysisCancelled", analysis, requirement)
        return analysis

    def edit(self, requirement_id: str, request: dict[str, Any]) -> dict[str, Any]:
        self.requirement_ingestion.update(
            requirement_id,
            title=str(request.get("title") or "").strip(),
            content=str(request.get("content") or request.get("planningRequirement") or "").strip(),
            actor=str(request.get("actor") or "HEI User"),
        )
        result = self.analyze(requirement_id, force=True)
        result["fieldOrigins"] = {
            key: "User Edited"
            for key in (
                "businessGoals", "functionalRequirements", "nonFunctionalRequirements",
                "acceptanceCriteria", "risks", "dependencies", "businessRules",
                "actors", "openQuestions", "constraints", "assumptions",
            )
            if result.get(key)
        }
        if result.get("acceptanceCriteria"):
            result["acceptanceCriteriaState"].update({"origin": "User Edited", "status": "Approved"})
        self._save(requirement_id, result)
        return result

    def suggest_acceptance_criteria(self, requirement_id: str, actor: str = "") -> dict[str, Any]:
        analysis = self._require_analysis(requirement_id)
        requirement = self.requirement_ingestion.get(requirement_id) or {}
        if not self._versions_current(analysis):
            analysis = self.analyze(requirement_id, force=True)
        if analysis.get("acceptanceCriteriaState", {}).get("state") == "SourceProvided":
            raise ValueError(
                "Source-provided Acceptance Criteria are already authoritative. Edit the source requirement to change them."
            )
        reasoning_context = self._acceptance_context_for_analysis(requirement, analysis)
        if self.project_intelligence_analyzer:
            project_reasoning = self.project_intelligence_analyzer.generate_acceptance_criteria(
                requirement, analysis, reasoning_context,
            )
            if self._project_intelligence_shadow_mode():
                reasoning = self._reason_about_acceptance(requirement, analysis, reasoning_context)
                reasoning.setdefault("diagnostics", {})["projectIntelligenceShadow"] = project_reasoning
            else:
                reasoning = project_reasoning
        else:
            reasoning = self._reason_about_acceptance(requirement, analysis, reasoning_context)
        suggestions = self._acceptance_suggestions_from_reasoning(reasoning, analysis)
        generation_mode = (
            "ProjectIntelligence"
            if suggestions and reasoning.get("provider") == "Project Intelligence"
            else "AI"
            if suggestions
            else "DeterministicFallback"
        )
        if not suggestions:
            suggestions = self.acceptance_engine.generate(analysis, requirement)
            for suggestion in suggestions:
                suggestion.update({
                    "origin": "Deterministic Fallback",
                    "provider": "Deterministic",
                    "model": "",
                    "promptVersion": "acceptance-deterministic-fallback-v1",
                    "confidence": min(float(suggestion.get("confidence") or 0.55), 0.55),
                    "confidenceBasis": "Rule-based mapping to supplied requirement evidence.",
                    "contextVersion": reasoning_context.get("contextVersion"),
                    "knowledgeVersion": (reasoning_context.get("sourceVersions") or {}).get("projectKnowledgeVersion"),
                    "repositoryRevision": (
                        ((reasoning_context.get("sourceVersions") or {}).get("repositoryMarkdown") or {}).get("repositoryRevision")
                        if isinstance((reasoning_context.get("sourceVersions") or {}).get("repositoryMarkdown"), dict)
                        else None
                    ) or (reasoning_context.get("sourceVersions") or {}).get("repositorySnapshotVersion"),
                })
        reasoning_diagnostics = reasoning.get("diagnostics") if isinstance(reasoning.get("diagnostics"), dict) else {}
        analysis.setdefault("acceptanceDiagnostics", {}).update({
            "generationMode": generation_mode,
            "reasoningMode": str(reasoning.get("reasoningMode") or "Deterministic"),
            "provider": str(reasoning.get("provider") or "Deterministic"),
            "model": str(reasoning.get("model") or ""),
            "promptVersion": str(reasoning.get("promptVersion") or ""),
            "warnings": list(reasoning.get("warnings") or []),
            "engineeringContextId": reasoning_context.get("contextId"),
            "engineeringContextVersion": reasoning_context.get("contextVersion"),
            "projectIntelligenceUsed": bool(reasoning_context.get("projectIntelligence")),
            "repositoryEvidenceUsed": bool(reasoning_context.get("repository")),
            "markdownEvidenceUsed": bool(
                (reasoning_context.get("repository_markdown_context") or {}).get("selected")
            ),
            "degraded": generation_mode == "DeterministicFallback",
            "retryAvailable": generation_mode == "DeterministicFallback",
            "projectIntelligencePrimary": bool(self.project_intelligence_analyzer),
            "projectIntelligenceDiagnostics": reasoning_diagnostics,
            "fallbackReason": (list(reasoning.get("warnings") or []) or [""])[0],
        })
        if not suggestions:
            analysis["acceptanceCriteriaSuggestions"] = []
            analysis["acceptanceCriteriaState"] = {
                "state": "Missing",
                "origin": "",
                "status": "NeedsUserInput",
                "description": (
                    "HEI could not identify enough business-observable evidence to generate "
                    "Acceptance Criteria. Add a specific action or expected outcome."
                ),
            }
            missing = list(analysis.get("missingInformation") or [])
            if not any(item.get("field") == "Generation Evidence" for item in missing):
                missing.append({
                    "field": "Generation Evidence",
                    "status": "Missing",
                    "reason": "Add a specific business action or observable outcome.",
                    "blocksGeneration": True,
                })
            analysis["missingInformation"] = missing
            analysis.setdefault("acceptanceDiagnostics", {})["generationStatus"] = "InsufficientEvidence"
            self._reset_review(analysis)
            self._refresh_acceptance_projection(analysis, requirement)
            self._save(requirement_id, analysis)
            self._publish_review("AcceptanceCriteriaSuggestionUnavailable", analysis, requirement)
            return analysis
        analysis["acceptanceCriteriaSuggestions"] = suggestions
        origin = (
            "Project Intelligence Generated"
            if generation_mode == "ProjectIntelligence"
            else "AI Enhanced"
            if generation_mode == "AI"
            else "Deterministic Fallback"
        )
        analysis["acceptanceCriteriaState"] = {
            "state": "AISuggested",
            "origin": origin,
            "status": "PendingReview",
            "description": (
                f"Acceptance Criteria were generated by {analysis['acceptanceDiagnostics']['provider']} "
                "and require explicit review."
                if generation_mode in {"AI", "ProjectIntelligence"}
                else "Acceptance Criteria were generated by HEI's deterministic fallback and require explicit review."
            ),
            "generatedBy": actor or "HEI",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
        self._reset_review(analysis)
        self._refresh_acceptance_projection(analysis, requirement)
        self._save(requirement_id, analysis)
        self._publish_review("AcceptanceCriteriaSuggested", analysis, requirement)
        return analysis

    def update_acceptance_criteria_suggestions(
        self, requirement_id: str, criteria: list[Any], actor: str = "",
    ) -> dict[str, Any]:
        analysis = self._require_analysis(requirement_id)
        requirement = self.requirement_ingestion.get(requirement_id) or {}
        if analysis.get("acceptanceCriteriaState", {}).get("state") != "AISuggested":
            raise ValueError("Generate suggested Acceptance Criteria before editing them.")
        normalized = []
        for index, item in enumerate(criteria):
            value = dict(item) if isinstance(item, dict) else {"text": str(item)}
            text = str(value.get("text") or "").strip()
            if not text:
                continue
            normalized.append({
                **self.acceptance_engine.normalize_edited(
                    value,
                    text=text,
                    order=index + 1,
                ),
                "criterionId": str(value.get("criterionId") or f"ac_{uuid4().hex}"),
            })
        if not normalized:
            raise ValueError("At least one suggested Acceptance Criterion is required.")
        analysis["acceptanceCriteriaSuggestions"] = normalized
        analysis["acceptanceCriteriaState"].update({
            "origin": "User Edited", "status": "PendingReview",
            "description": "HEI suggestions were edited by a user and require explicit approval.",
            "editedBy": actor or "HEI User",
            "editedAt": datetime.now(timezone.utc).isoformat(),
        })
        self._reset_review(analysis)
        self._refresh_acceptance_projection(analysis, requirement)
        self._save(requirement_id, analysis)
        return analysis

    def approve_acceptance_criteria(self, requirement_id: str, actor: str) -> dict[str, Any]:
        analysis = self._require_analysis(requirement_id)
        requirement = self.requirement_ingestion.get(requirement_id) or {}
        suggestions = list(analysis.get("acceptanceCriteriaSuggestions") or [])
        if not suggestions:
            raise ValueError("No suggested Acceptance Criteria are available for approval.")
        origin = str(analysis.get("acceptanceCriteriaState", {}).get("origin") or "AI Suggested")
        analysis["acceptanceCriteria"] = [str(item.get("text") or "").strip() for item in suggestions if str(item.get("text") or "").strip()]
        for item in suggestions:
            item["status"] = "Approved"
        analysis["acceptanceCriteriaSuggestions"] = suggestions
        analysis["acceptanceCriteriaRecords"] = suggestions
        analysis["acceptanceCriteriaState"].update({
            "state": "AISuggested",
            "origin": origin,
            "status": "Approved",
            "description": "Suggested Acceptance Criteria were reviewed and approved for Planning.",
            "approvedBy": actor or "HEI User",
            "approvedAt": datetime.now(timezone.utc).isoformat(),
        })
        analysis.setdefault("fieldOrigins", {})["acceptanceCriteria"] = origin
        analysis["missingAcceptanceCriteria"] = []
        self._reset_review(analysis)
        self._refresh_acceptance_projection(analysis, requirement)
        self._save(requirement_id, analysis)
        self._publish_review("AcceptanceCriteriaApproved", analysis, requirement)
        return analysis

    def discard_acceptance_criteria(self, requirement_id: str, actor: str, *, skipped: bool = False) -> dict[str, Any]:
        analysis = self._require_analysis(requirement_id)
        requirement = self.requirement_ingestion.get(requirement_id) or {}
        if analysis.get("acceptanceCriteriaState", {}).get("state") == "SourceProvided":
            raise ValueError("Source-provided Acceptance Criteria cannot be discarded as AI suggestions.")
        analysis["acceptanceCriteria"] = []
        analysis["acceptanceCriteriaRecords"] = []
        analysis["acceptanceCriteriaSuggestions"] = []
        status = "Skipped" if skipped else "Discarded"
        analysis["acceptanceCriteriaState"] = {
            "state": "Missing",
            "origin": "",
            "status": status,
            "description": "No Acceptance Criteria were provided in the source requirement.",
            f"{status.lower()}By": actor or "HEI User",
            f"{status.lower()}At": datetime.now(timezone.utc).isoformat(),
        }
        analysis.get("fieldOrigins", {}).pop("acceptanceCriteria", None)
        analysis["missingAcceptanceCriteria"] = [RequirementFinding(
            "No Acceptance Criteria were provided in the source requirement.",
            "Planning may continue with reduced testability and implementation confidence.",
            evidence="The source contains no criteria and generated suggestions were not approved.",
        ).to_dict()]
        self._reset_review(analysis)
        self._refresh_acceptance_projection(analysis, requirement)
        self._save(requirement_id, analysis)
        self._publish_review(f"AcceptanceCriteria{status}", analysis, requirement)
        return analysis

    def assert_approved(self, requirement_id: str) -> dict[str, Any]:
        analysis = self.get(requirement_id)
        requirement = self.requirement_ingestion.get(requirement_id)
        if not analysis or not requirement:
            raise ValueError("Review and approve Requirement Analysis before Planning.")
        valid = (
            analysis.get("reviewStatus") == "Approved"
            and analysis.get("approvedContentHash") == requirement.get("contentHash")
            and analysis.get("approvedContextVersion") == requirement.get("contextVersion")
        )
        if not valid:
            raise ValueError("Requirement Analysis approval is required before Planning.")
        return analysis

    def _require_analysis(self, requirement_id: str) -> dict[str, Any]:
        analysis = self.get(requirement_id)
        if not analysis:
            if not self.requirement_ingestion.get(requirement_id):
                raise ValueError("Requirement context was not found. Ingest the source before analysis.")
            analysis = self.analyze(requirement_id, force=True)
        return analysis

    def _reason_about_requirement(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
        engineering_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.reasoning_engine:
            return self._reasoning_not_requested()
        try:
            result = self.reasoning_engine.analyze(
                "Requirement Evidence Synthesis",
                engineering_context or self._reasoning_context(requirement, analysis),
                user_requirement=str(analysis.get("planningRequirement") or ""),
                provider="Auto",
                correlation_id=str(requirement.get("correlationId") or ""),
            )
            return self._reasoning_projection(result)
        except Exception as error:
            return self._reasoning_failure(error)

    def _reason_about_intent(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.reasoning_engine:
            return self._reasoning_not_requested()
        metadata = requirement.get("metadata") or {}
        attributes = metadata.get("attributes") or {}
        bounded_context = {
            "contextType": "RequirementIntentInput",
            "contextId": f"requirement-intent-{requirement.get('requirementId')}",
            "contextVersion": requirement.get("contextVersion") or "1.0",
            "requirement": {
                "requirementId": requirement.get("requirementId"),
                "title": requirement.get("title"),
                "sourceType": requirement.get("sourceType"),
                "normalizedRequirement": requirement.get("normalizedRequirement"),
            },
            "metadata": {
                "projectId": metadata.get("projectId") or requirement.get("projectId"),
                "projectName": metadata.get("projectName"),
                "repositoryId": metadata.get("repositoryId"),
                "repositoryName": (metadata.get("attributes") or {}).get("repositoryName"),
                "sourceType": requirement.get("sourceType"),
                "projectSummary": {
                    key: attributes.get(key)
                    for key in (
                        "projectDescription", "domain", "product", "technology",
                        "areaPath", "iterationPath",
                    )
                    if attributes.get(key)
                },
            },
        }
        try:
            return self.reasoning_engine.analyze(
                "Requirement Intent Analysis",
                bounded_context,
                user_requirement=str(
                    requirement.get("normalizedRequirement")
                    or analysis.get("planningRequirement")
                    or ""
                ),
                provider="Auto",
                correlation_id=str(requirement.get("correlationId") or ""),
            )
        except Exception as error:
            return self._reasoning_failure(error)

    def _reason_about_acceptance(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
        engineering_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.reasoning_engine:
            return self._reasoning_not_requested()
        try:
            context = engineering_context or self._reasoning_context(requirement, analysis)
            return self.reasoning_engine.analyze(
                "Acceptance Criteria Generation",
                context,
                user_requirement=str(analysis.get("planningRequirement") or ""),
                provider="Auto",
                correlation_id=str(requirement.get("correlationId") or ""),
            )
        except Exception as error:
            return self._reasoning_failure(error)

    def _acceptance_context_for_analysis(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        stored = analysis.get("engineeringContext")
        lineage = analysis.get("analysisLineage") or {}
        if (
            isinstance(stored, dict)
            and stored.get("contextId")
            and stored.get("contextVersion")
            and stored.get("contextId") == lineage.get("contextId")
            and stored.get("contextVersion") == lineage.get("contextVersion")
        ):
            return stored
        refreshed = self._reasoning_context(requirement, analysis)
        bounded = self._acceptance_context(refreshed)
        analysis["engineeringContext"] = bounded
        return bounded

    @staticmethod
    def _acceptance_context(context: dict[str, Any]) -> dict[str, Any]:
        """Persist the bounded evidence used by analysis for repeatable AC generation."""

        allowed = (
            "contextId", "contextVersion", "requirement", "repository",
            "projectIntelligence", "repository_markdown_context",
            "relevantDocumentation", "knowledge_synthesis", "azureDevOps",
            "engineeringMemory", "similarWork", "architecture", "dependencies",
            "impact", "reuse", "readiness", "sourceVersions", "rejectedContext",
        )
        return {
            key: context[key]
            for key in allowed
            if key in context
        }

    def _reasoning_context(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        canonical_requirement = self.engineering_intelligence.analyze_requirement(
            requirement, analysis,
        )
        selected = (analysis.get("repositorySuggestion") or {}).get("suggestedRepository")
        if isinstance(selected, dict) and selected:
            canonical_requirement["repository"] = dict(selected)
            canonical_requirement["repositoryId"] = selected.get("repositoryId")
        return self.engineering_intelligence.build_requirement_context(
            canonical_requirement,
            correlation_id=str(requirement.get("correlationId") or ""),
        )

    def _build_engineering_context(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self._reasoning_context(requirement, analysis)
        except Exception as error:
            analyze_requirement = getattr(
                self.engineering_intelligence, "analyze_requirement", None,
            )
            canonical_requirement = (
                analyze_requirement(requirement, analysis)
                if callable(analyze_requirement)
                else {
                    "requirementId": requirement.get("requirementId"),
                    "title": requirement.get("title"),
                    "planningRequirement": analysis.get("planningRequirement"),
                    "businessGoals": _strings(analysis.get("businessGoals")),
                    "functionalRequirements": _strings(analysis.get("functionalRequirements")),
                    "acceptanceCriteria": _strings(analysis.get("acceptanceCriteria")),
                    "requirementIntent": dict(analysis.get("requirementIntent") or {}),
                    "projectId": (requirement.get("metadata") or {}).get("projectId"),
                }
            )
            return {
                "contextId": f"engineering-context-unavailable-{requirement.get('requirementId')}",
                "contextVersion": str(requirement.get("contextVersion") or "1.0"),
                "requirement": canonical_requirement,
                "repository": {
                    "mode": "Unavailable",
                    "warnings": [f"Engineering discovery unavailable: {error}"],
                },
                "azureDevOps": {},
                "engineeringMemory": {},
                "similarWork": {},
                "architecture": {},
                "dependencies": {},
                "impact": {},
                "reuse": {},
                "readiness": {
                    "status": "ReadyWithRecommendations",
                    "warnings": ["Engineering discovery was unavailable; human review is required."],
                    "confidence": 35,
                },
                "sourceVersions": {
                    "requirementContextVersion": requirement.get("contextVersion"),
                },
            }

    @staticmethod
    def _reasoning_projection(result: dict[str, Any]) -> dict[str, Any]:
        recommendation = result.get("recommendation")
        return {
            "status": "Completed" if result.get("reasoningMode") == "AI" else "Fallback",
            "reasoningMode": str(result.get("reasoningMode") or "Deterministic"),
            "provider": str(result.get("provider") or "Deterministic"),
            "model": str(result.get("model") or ""),
            "promptVersion": str(result.get("promptVersion") or ""),
            "recommendation": recommendation if isinstance(recommendation, dict) else {},
            "insights": list(result.get("reasoning") or []),
            "alternatives": list(result.get("alternatives") or []),
            "warnings": list(result.get("warnings") or []),
            "confidence": dict(result.get("confidence") or {}),
            "evidence": list(result.get("evidence") or []),
            "telemetry": dict(result.get("telemetry") or {}),
            "diagnostics": dict(result.get("diagnostics") or {}),
        }

    @staticmethod
    def _requirement_intent(
        reasoning: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        recommendation = reasoning.get("recommendation") or {}
        candidate = (
            recommendation.get("requirementIntent")
            if isinstance(recommendation, dict)
            else {}
        )
        if not isinstance(candidate, dict):
            candidate = {}
        if candidate:
            return _normalize_intent(candidate)
        functional = _strings(analysis.get("functionalRequirements"))
        business = _strings(analysis.get("businessGoals"))
        words = _search_words(" ".join([*business, *functional]))
        return _normalize_intent({
            "intentSummary": analysis.get("requirementSummary"),
            "businessGoal": business[0] if business else "",
            "functionalIntent": functional,
            "entities": _strings(analysis.get("actors")),
            "primaryActor": (_strings(analysis.get("actors")) or [""])[0],
            "secondaryActors": _strings(analysis.get("actors"))[1:],
            "capabilities": [],
            "actions": functional,
            "concepts": words[:8],
            "searchKeywords": words[:12],
            "clarificationCandidates": [
                str(item.get("text") or "")
                for item in analysis.get("ambiguousRequirements") or []
                if isinstance(item, dict)
            ],
            "confidence": analysis.get("confidence") or 0,
        })

    @staticmethod
    def _apply_intent(analysis: dict[str, Any], intent: dict[str, Any]) -> None:
        business_goal = str(intent.get("businessGoal") or "").strip()
        if business_goal and not analysis.get("businessGoals"):
            analysis["businessGoals"] = [business_goal]
            analysis.setdefault("fieldOrigins", {})["businessGoals"] = "AI Inferred"
        functional = _strings(intent.get("functionalIntent"))
        if functional and not analysis.get("functionalRequirements"):
            analysis["functionalRequirements"] = functional
            analysis.setdefault("fieldOrigins", {})["functionalRequirements"] = "AI Inferred"

    @staticmethod
    def _apply_evidence_synthesis(
        analysis: dict[str, Any],
        reasoning: dict[str, Any],
    ) -> None:
        if reasoning.get("reasoningMode") != "AI":
            return
        recommendation = reasoning.get("recommendation") or {}
        if not isinstance(recommendation, dict):
            return
        mapping = {
            "functionalRequirements": "functionalRequirements",
            "nonFunctionalRequirements": "nonFunctionalRequirements",
            "businessRules": "businessRules",
            "constraints": "constraints",
            "dependencies": "dependencies",
            "risks": "risks",
            "openQuestions": "openQuestions",
        }
        for source, target in mapping.items():
            additions = _strings(recommendation.get(source))
            if additions:
                analysis[target] = _unique([*_strings(analysis.get(target)), *additions])
                analysis.setdefault("fieldOrigins", {}).setdefault(target, "Evidence Backed")
        business_goal = str(recommendation.get("businessGoal") or "").strip()
        functional = _strings(analysis.get("functionalRequirements"))
        current_business = _strings(analysis.get("businessGoals"))
        current_duplicates_functional = bool(
            current_business and any(_normalized_phrase(current_business[0]) == _normalized_phrase(item) for item in functional)
        )
        if business_goal and not any(
            _normalized_phrase(business_goal) == _normalized_phrase(item) for item in functional
        ) and (not current_business or current_duplicates_functional):
            analysis["businessGoals"] = [business_goal]
            analysis.setdefault("fieldOrigins", {})["businessGoals"] = "Project Intelligence Generated"
        actors = _unique([
            str(recommendation.get("primaryActor") or "").strip(),
            *_strings(recommendation.get("secondaryActors")),
        ])
        if actors:
            analysis["actors"] = _unique([*_strings(analysis.get("actors")), *actors])
            analysis.setdefault("fieldOrigins", {}).setdefault("actors", "Project Intelligence Generated")
        intent = analysis.get("requirementIntent") if isinstance(analysis.get("requirementIntent"), dict) else {}
        intent["capabilities"] = _unique([*_strings(intent.get("capabilities")), *_strings(recommendation.get("capabilities"))])
        intent["possibleRepositoryTerms"] = _unique([*_strings(intent.get("possibleRepositoryTerms")), *_strings(recommendation.get("repositorySearchHints"))])
        intent["possibleMarkdownSearchTerms"] = _unique([*_strings(intent.get("possibleMarkdownSearchTerms")), *_strings(recommendation.get("markdownSearchHints"))])
        intent["possibleAzureDevOpsSearchTerms"] = _unique([*_strings(intent.get("possibleAzureDevOpsSearchTerms")), *_strings(recommendation.get("azureDevOpsSearchHints"))])
        analysis["requirementIntent"] = intent
        if recommendation.get("executiveSummary"):
            analysis["requirementSummary"] = str(recommendation["executiveSummary"])
        analysis["evidenceSynthesis"] = {
            "repositoryFindings": _strings(recommendation.get("repositoryFindings")),
            "architectureFindings": _strings(recommendation.get("architectureFindings")),
            "reuseOpportunities": _strings(recommendation.get("reuseOpportunities")),
            "affectedEngineeringElements": _strings(recommendation.get("affectedEngineeringElements")),
            "missingInformation": _strings(recommendation.get("missingInformation")),
            "engineeringInsights": _strings(recommendation.get("engineeringInsights")),
            "evidence": list(reasoning.get("evidence") or []),
        }

    @staticmethod
    def _apply_statement_governance(
        analysis: dict[str, Any], governance: dict[str, Any],
    ) -> None:
        analysis["functionalRequirements"] = _strings(governance.get("acceptedFunctionalRequirements"))
        analysis["nonFunctionalRequirements"] = _strings(governance.get("acceptedNonFunctionalRequirements"))
        analysis["suggestedEnhancements"] = list(governance.get("suggestedEnhancements") or [])
        analysis["candidateNonFunctionalRequirements"] = list(governance.get("candidateNonFunctionalRequirements") or [])
        # Preserve source extraction semantics. Inferred business outcomes and
        # candidate actors live in statementGovernance/analysisDocument where
        # their provenance remains visible; they do not become source facts.

    def _engineering_discovery(self, context: dict[str, Any]) -> dict[str, Any]:
        markdown = context.get("repository_markdown_context") or {}
        repository = context.get("repository") or {}
        ado = context.get("azureDevOps") or {}
        memory = context.get("engineeringMemory") or {}
        compatibility = {
            "contextId": context.get("contextId"),
            "contextVersion": context.get("contextVersion"),
            "repository": {
                "mode": repository.get("mode"),
                "snapshotVersion": repository.get("repositorySnapshotVersion"),
                "modules": repository.get("affectedModules") or [],
                "files": repository.get("files") or [],
                "services": repository.get("services") or [],
                "apis": repository.get("apiEndpoints") or [],
            },
            "markdown": markdown,
            "azureDevOps": {
                "workItems": ado.get("existingPlanning") or [],
                "currentIteration": ado.get("currentIteration") or {},
            },
            "knowledge": context.get("projectIntelligence") or {},
            "memory": {"matches": memory.get("matches") or []},
            "similarWork": context.get("similarWork") or {},
            "architecture": context.get("architecture") or {},
            "dependencies": context.get("dependencies") or {},
            "rejectedContext": context.get("rejectedContext") or [],
        }
        builder = getattr(self.engineering_intelligence, "build_discovery_report", None)
        report = builder(context) if callable(builder) else {}
        return {**compatibility, "report": report}

    @staticmethod
    def _analysis_lineage(
        requirement: dict[str, Any],
        intent: dict[str, Any],
        synthesis: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        source_versions = context.get("sourceVersions") or {}
        primary = (
            synthesis
            if synthesis.get("reasoningMode") == "AI"
            else intent
            if intent.get("reasoningMode") == "AI"
            else synthesis
        )
        return {
            "provider": primary.get("provider") or "Deterministic",
            "model": primary.get("model") or "",
            "intentProvider": intent.get("provider") or "Deterministic",
            "intentModel": intent.get("model") or "",
            "synthesisProvider": synthesis.get("provider") or "Deterministic",
            "synthesisModel": synthesis.get("model") or "",
            "intentPromptVersion": intent.get("promptVersion") or "",
            "synthesisPromptVersion": synthesis.get("promptVersion") or "",
            "contextId": context.get("contextId"),
            "contextVersion": context.get("contextVersion"),
            "knowledgeVersion": source_versions.get("projectKnowledgeVersion"),
            "repositoryRevision": (
                source_versions.get("repositoryMarkdown") or {}
            ).get("repositoryRevision") or source_versions.get("repositorySnapshotVersion"),
            "requirementContextVersion": requirement.get("contextVersion"),
            "analysisVersion": "requirement-analysis-v2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _reasoning_not_requested() -> dict[str, Any]:
        return {
            "status": "NotConfigured",
            "reasoningMode": "Deterministic",
            "provider": "Deterministic",
            "model": "",
            "promptVersion": "",
            "recommendation": {},
            "insights": [],
            "alternatives": [],
            "warnings": ["Reasoning AI was not configured for this service."],
            "confidence": {},
        }

    @staticmethod
    def _project_intelligence_shadow_mode() -> bool:
        return os.getenv("AI_GEN_REQUIREMENT_PI_SHADOW_MODE", "").strip().lower() in {
            "1", "true", "yes", "on",
        }

    @staticmethod
    def _reasoning_failure(error: Exception) -> dict[str, Any]:
        return {
            "status": "Fallback",
            "reasoningMode": "Deterministic",
            "provider": "Deterministic",
            "model": "",
            "promptVersion": "",
            "recommendation": {},
            "insights": [],
            "alternatives": [],
            "warnings": [f"Reasoning provider unavailable: {error}"],
            "confidence": {},
        }

    def _acceptance_suggestions_from_reasoning(
        self,
        reasoning: dict[str, Any],
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if reasoning.get("reasoningMode") != "AI":
            return []
        recommendation = reasoning.get("recommendation")
        if not isinstance(recommendation, dict):
            return []
        raw_criteria = recommendation.get("acceptanceCriteria")
        if not isinstance(raw_criteria, list):
            return []
        functional = [
            str(item).strip()
            for item in analysis.get("functionalRequirements") or []
            if str(item).strip()
        ]
        suggestions: list[dict[str, Any]] = []
        for index, item in enumerate(raw_criteria):
            value = dict(item) if isinstance(item, dict) else {"text": str(item)}
            text = str(value.get("text") or "").strip()
            if not text or not functional:
                continue
            mapped = str(value.get("mappedFunctionalRequirement") or "").strip()
            if mapped not in functional:
                mapped = functional[min(index, len(functional) - 1)]
            confidence = value.get("confidence")
            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError):
                confidence_value = 0.8
            if confidence_value > 1:
                confidence_value /= 100
            evidence = value.get("evidence") if isinstance(value.get("evidence"), list) else []
            if not evidence:
                evidence = [{
                    "requirementSentence": mapped,
                    "matchedPhrase": mapped,
                    "confidence": max(0.0, min(1.0, confidence_value)),
                    "source": "Engineering Context",
                }]
            origin = str(value.get("origin") or (
                "Project Intelligence Generated"
                if reasoning.get("provider") == "Project Intelligence"
                else "AI Enhanced"
            ))
            normalized = self.acceptance_engine.normalize_edited(
                {
                    **value,
                    "mappedFunctionalRequirement": mapped,
                    "evidence": evidence,
                    "origin": origin,
                },
                text=text,
                order=len(suggestions) + 1,
            )
            normalized.update({
                "origin": origin,
                "status": "PendingReview",
                "type": str(value.get("type") or "Functional"),
                "confidence": max(0.0, min(1.0, confidence_value)),
                "provider": value.get("provider") or reasoning.get("provider"),
                "model": value.get("model") or reasoning.get("model"),
                "promptVersion": value.get("promptVersion") or reasoning.get("promptVersion"),
                "confidenceBasis": value.get("confidenceBasis") or "Mapped to supplied functional evidence.",
                "contextVersion": value.get("contextVersion"),
                "knowledgeVersion": value.get("knowledgeVersion"),
                "repositoryRevision": value.get("repositoryRevision"),
            })
            normalized.pop("editedFrom", None)
            suggestions.append(normalized)
        return suggestions

    @staticmethod
    def _versions_current(analysis: dict[str, Any]) -> bool:
        return (
            analysis.get("diagnostics", {}).get("engine")
            == "DeterministicRequirementAnalysisV3"
            and analysis.get("acceptanceDiagnostics", {}).get("engine")
            == "IntelligentAcceptanceCriteriaV1"
            and analysis.get("analysisLineage", {}).get("analysisVersion")
            == "requirement-analysis-v2"
            and analysis.get("analysisDocument", {}).get("schemaVersion")
            == "hei-requirement-analysis-v2"
            and analysis.get("statementGovernance", {}).get("schemaVersion")
            == "hei-statement-governance-v1"
        )

    def _restore_reviewed_acceptance(
        self,
        analysis: dict[str, Any],
        snapshot: dict[str, Any],
        requirement: dict[str, Any],
    ) -> None:
        state = snapshot.get("acceptanceCriteriaState") or {}
        if state.get("state") == "SourceProvided":
            return
        analysis["acceptanceCriteria"] = list(snapshot.get("acceptanceCriteria") or [])
        analysis["acceptanceCriteriaRecords"] = list(snapshot.get("acceptanceCriteriaRecords") or [])
        analysis["acceptanceCriteriaSuggestions"] = list(snapshot.get("acceptanceCriteriaSuggestions") or [])
        analysis["acceptanceCriteriaState"] = dict(state)
        origin = snapshot.get("acceptanceCriteriaOrigin")
        if origin:
            analysis.setdefault("fieldOrigins", {})["acceptanceCriteria"] = origin
        else:
            analysis.get("fieldOrigins", {}).pop("acceptanceCriteria", None)
        if analysis["acceptanceCriteria"]:
            analysis["missingAcceptanceCriteria"] = []
        self._refresh_acceptance_projection(analysis, requirement)
        self._save(str(analysis.get("requirementId") or ""), analysis)

    @staticmethod
    def _reset_review(analysis: dict[str, Any]) -> None:
        analysis.update({
            "reviewStatus": "Pending", "approvedBy": "", "approvedAt": "",
            "approvedContentHash": "", "approvedContextVersion": "",
        })

    def _refresh_acceptance_projection(
        self, analysis: dict[str, Any], requirement: dict[str, Any],
    ) -> None:
        values = {
            "business_goals": list(analysis.get("businessGoals") or []),
            "functional_requirements": list(analysis.get("functionalRequirements") or []),
            "non_functional_requirements": list(analysis.get("nonFunctionalRequirements") or []),
            "acceptance_criteria": list(analysis.get("acceptanceCriteria") or []),
            "actors": list(analysis.get("actors") or []),
            "business_rules": list(analysis.get("businessRules") or []),
            "constraints": list(analysis.get("constraints") or []),
            "dependencies": list(analysis.get("dependencies") or []),
            "risks": list(analysis.get("risks") or []),
            "open_questions": list(analysis.get("openQuestions") or []),
            "assumptions": list(analysis.get("assumptions") or []),
        }
        ambiguous = list(analysis.get("ambiguousRequirements") or [])
        conflicts = list(analysis.get("conflictingRequirements") or [])
        duplicates = list(analysis.get("duplicateRequirements") or [])
        missing = list(analysis.get("missingAcceptanceCriteria") or [])
        state = analysis.get("acceptanceCriteriaState") or {}
        suggestions_pending = (
            state.get("state") == "AISuggested"
            and state.get("status") == "PendingReview"
        )
        if suggestions_pending:
            # Suggestions resolve the absence finding, but remain unofficial until reviewed.
            missing = []
            analysis["missingAcceptanceCriteria"] = []
        score = self.engine._quality_score(str(requirement.get("title") or ""), values, ambiguous, conflicts, duplicates)
        readiness = self.engine._readiness(values, score, missing, ambiguous, conflicts)
        if suggestions_pending:
            readiness["status"] = "ReadyWithRecommendations"
            readiness["readyForPlanning"] = True
            readiness["warnings"] = [
                "Generated Acceptance Criteria require approval, editing, or discard before Planning approval.",
                *[warning for warning in readiness["warnings"] if "Acceptance Criteria" not in warning],
            ]
        analysis["requirementQualityScore"] = score
        analysis["planningReadiness"] = readiness
        analysis["planningRequirement"] = self.engine._planning_requirement(
            str(requirement.get("title") or ""), values, [
                RequirementFinding(
                    str(item.get("text") or ""),
                    str(item.get("reason") or ""),
                    str(item.get("evidence") or ""),
                    float(item.get("confidence") or 1),
                )
                for item in missing if isinstance(item, dict)
            ],
        )
        self.acceptance_engine.refresh_projection(analysis)

    def _save(self, requirement_id: str, analysis: dict[str, Any]) -> None:
        values = self.store.read()
        values[requirement_id] = analysis
        self.store.write(values)

    def _publish_review(self, event_type: str, analysis: dict[str, Any], requirement: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "RequirementIntelligence",
            "projectId": requirement.get("metadata", {}).get("projectId", ""),
            "correlationId": requirement.get("correlationId", ""),
            "payload": {"requirementId": analysis.get("requirementId"), "analysisId": analysis.get("analysisId"), "reviewStatus": analysis.get("reviewStatus")},
        })

    def _publish(self, analysis: dict[str, Any], requirement: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": "RequirementAnalyzed",
            "source": "RequirementIntelligence",
            "projectId": requirement.get("metadata", {}).get("projectId", ""),
            "correlationId": requirement.get("correlationId", ""),
            "payload": {
                "requirementId": analysis.get("requirementId"),
                "analysisId": analysis.get("analysisId"),
                "planningReadiness": analysis.get("planningReadiness", {}).get("status"),
                "qualityScore": analysis.get("requirementQualityScore"),
            },
        })


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _normalized_phrase(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _search_words(value: str) -> list[str]:
    ignored = {
        "about", "after", "before", "from", "into", "must", "should",
        "that", "their", "these", "they", "this", "users", "with",
    }
    return _unique([
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", value)
        if len(token) > 3 and token.casefold() not in ignored
    ])


def _normalize_intent(value: dict[str, Any]) -> dict[str, Any]:
    list_fields = (
        "functionalIntent", "entities", "secondaryActors", "capabilities", "actions",
        "concepts", "businessTerminology", "explicitConstraints",
        "possibleAssumptions", "ambiguities", "riskIndicators",
        "technologyConcepts", "domainSynonyms", "searchKeywords",
        "possibleModuleNames", "possibleFeatureNames", "possibleApis",
        "possibleRepositoryTerms", "possibleAzureDevOpsSearchTerms",
        "possibleMarkdownSearchTerms", "clarificationCandidates",
    )
    confidence = value.get("confidence") or 0
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    if confidence_value > 1:
        confidence_value /= 100
    result = {
        "intentSummary": str(value.get("intentSummary") or "").strip(),
        "businessGoal": str(value.get("businessGoal") or "").strip(),
        "primaryActor": str(value.get("primaryActor") or "").strip(),
        "confidence": round(max(0.0, min(1.0, confidence_value)), 2),
    }
    for field_name in list_fields:
        result[field_name] = _unique(_strings(value.get(field_name)))
    return result
