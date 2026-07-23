"""Persistence and orchestration for Requirement Analysis."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
from uuid import uuid4

from backend.platform.shared import JsonMapStore
from backend.engineering_intelligence import EngineeringIntelligenceService
from backend.requirement_intake.ingestion import RequirementIngestionService

from .acceptance_criteria import IntelligentAcceptanceCriteriaEngine
from .engine import RequirementAnalysisEngine
from .models import RequirementFinding


class RequirementAnalysisService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        requirement_ingestion: RequirementIngestionService,
        engine: RequirementAnalysisEngine | None = None,
        acceptance_engine: IntelligentAcceptanceCriteriaEngine | None = None,
        repository_detector: Any | None = None,
        engineering_intelligence: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.requirement_ingestion = requirement_ingestion
        self.engine = engine or RequirementAnalysisEngine()
        self.acceptance_engine = acceptance_engine or IntelligentAcceptanceCriteriaEngine()
        self.repository_detector = repository_detector
        self.engineering_intelligence = engineering_intelligence or EngineeringIntelligenceService(
            repository_detector=repository_detector,
        )
        self.platform = platform

    def analyze(self, requirement_id: str, *, force: bool = False) -> dict[str, Any]:
        requirement = self.requirement_ingestion.get(requirement_id)
        if not requirement:
            raise ValueError("Requirement context was not found. Ingest the source before analysis.")
        existing = self.get(requirement_id)
        acceptance_version_current = (
            (existing or {}).get("acceptanceDiagnostics", {}).get("engine")
            == "IntelligentAcceptanceCriteriaV1"
        )
        if existing and not force and acceptance_version_current and existing.get("contentHash") == requirement.get("contentHash") and existing.get("contextVersion") == requirement.get("contextVersion"):
            return existing
        result = self.engine.analyze(requirement).to_dict()
        result.update(self.acceptance_engine.understand(result, requirement))
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
        values = self.store.read()
        values[requirement_id] = result
        self.store.write(values)
        self._publish(result, requirement)
        return result

    def get(self, requirement_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(requirement_id)
        return dict(value) if isinstance(value, dict) else None

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
                "Review the AI Suggested Acceptance Criteria. Approve, edit, or discard them before Planning."
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
        if analysis.get("acceptanceCriteriaState", {}).get("state") == "SourceProvided":
            raise ValueError(
                "Source-provided Acceptance Criteria are already authoritative. Edit the source requirement to change them."
            )
        suggestions = self.acceptance_engine.generate(analysis, requirement)
        if not suggestions:
            raise ValueError(
                "No evidence-backed Acceptance Criteria could be generated. "
                "Add a specific functional requirement, actor, action, or observable outcome."
            )
        analysis["acceptanceCriteriaSuggestions"] = suggestions
        analysis["acceptanceCriteriaState"] = {
            "state": "AISuggested",
            "origin": "AI Suggested",
            "status": "PendingReview",
            "description": "Acceptance Criteria were generated by HEI and require explicit review.",
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
            raise ValueError("Requirement analysis was not found. Analyze the requirement first.")
        return analysis

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
        score = self.engine._quality_score(str(requirement.get("title") or ""), values, ambiguous, conflicts, duplicates)
        readiness = self.engine._readiness(values, score, missing, ambiguous, conflicts)
        state = analysis.get("acceptanceCriteriaState") or {}
        if state.get("state") == "AISuggested" and state.get("status") == "PendingReview":
            readiness["status"] = "ReadyWithRecommendations"
            readiness["readyForPlanning"] = True
            readiness["warnings"] = [
                "AI Suggested Acceptance Criteria require approval, editing, or discard before Planning approval.",
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
