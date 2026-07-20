"""Persistence and orchestration for Requirement Analysis."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from backend.platform.shared import JsonMapStore
from backend.requirement_intake.ingestion import RequirementIngestionService

from .engine import RequirementAnalysisEngine


class RequirementAnalysisService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        requirement_ingestion: RequirementIngestionService,
        engine: RequirementAnalysisEngine | None = None,
        repository_detector: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.requirement_ingestion = requirement_ingestion
        self.engine = engine or RequirementAnalysisEngine()
        self.repository_detector = repository_detector
        self.platform = platform

    def analyze(self, requirement_id: str, *, force: bool = False) -> dict[str, Any]:
        requirement = self.requirement_ingestion.get(requirement_id)
        if not requirement:
            raise ValueError("Requirement context was not found. Ingest the source before analysis.")
        existing = self.get(requirement_id)
        if existing and not force and existing.get("contentHash") == requirement.get("contentHash") and existing.get("contextVersion") == requirement.get("contextVersion"):
            return existing
        result = self.engine.analyze(requirement).to_dict()
        if self.repository_detector:
            suggestion = self.repository_detector.detect_requirement(requirement, result)
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
        selected = (analysis.get("repositorySuggestion") or {}).get("suggestedRepository") or {}
        current_repository_id = str(requirement.get("metadata", {}).get("repositoryId") or "")
        selected_repository_id = str(selected.get("repositoryId") or "")
        if selected_repository_id and selected_repository_id != current_repository_id:
            self.requirement_ingestion.update_repository(
                requirement_id,
                repository_id=selected_repository_id,
                repository_name=str(selected.get("name") or ""),
                actor=actor or "HEI User",
            )
            analysis = self.analyze(requirement_id, force=True)
            requirement = self.requirement_ingestion.get(requirement_id) or requirement
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
        return self.analyze(requirement_id, force=True)

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
