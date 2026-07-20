"""Requirement Intelligence to Planning Intelligence integration boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.platform.shared import JsonMapStore
from backend.requirement_analysis.summary import build_requirement_summary


class RequirementPlanningService:
    """Generates Planning Packs exclusively from approved Requirement Summaries."""

    def __init__(
        self,
        store: JsonMapStore,
        *,
        requirement_ingestion: Any,
        requirement_analysis: Any,
        requirement_intake: Any,
        estimation_engine: Any,
        artifact_provider: Any,
        repository_intelligence: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.requirement_ingestion = requirement_ingestion
        self.requirement_analysis = requirement_analysis
        self.requirement_intake = requirement_intake
        self.estimation_engine = estimation_engine
        self.artifact_provider = artifact_provider
        self.repository_intelligence = repository_intelligence
        self.platform = platform

    def from_requirement(self, request: dict[str, Any]) -> dict[str, Any]:
        result = self.generate(request)
        return {**result, "entryPoint": "RequirementIntelligence"}

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        requirement_id = _required_requirement_id(request)
        summary = self._approved_summary(requirement_id)
        existing = self.store.read().get(requirement_id)
        if (
            isinstance(existing, dict)
            and request.get("force") is not True
            and existing.get("requirementContextVersion") == summary["contextVersion"]
            and existing.get("analysisId") == summary["analysisId"]
        ):
            return _public(existing)

        actor = _text(request.get("actor")) or "HEI User"
        generated = self.requirement_intake.submit({
            "requirementContextId": requirement_id,
            "actor": actor,
            "correlationId": summary["correlationId"],
        })
        artifact = self._artifact(generated["planningPackId"])
        repository_context = self._repository_context(summary)
        estimate = self.estimation_engine.estimate({
            "planningPackage": {
                "id": generated["planningPackId"],
                "type": "Epic",
                "title": summary["title"],
                "description": summary["planningRequirement"],
                "projectId": summary["projectId"],
                "acceptanceCriteria": summary["acceptanceCriteria"],
                "dependencies": summary["dependencies"],
                "risks": summary["risks"],
            },
            "acceptanceCriteria": summary["acceptanceCriteria"],
            "dependencyAnalysis": summary["dependencies"],
            "riskAnalysis": summary["risks"],
            "repositoryContext": repository_context,
        }, correlation_id=summary["correlationId"])
        preview = self._preview(summary, generated, artifact, estimate, repository_context)
        record = {
            "schemaVersion": "hei-requirement-planning-v1",
            "requirementId": requirement_id,
            "requirementContextVersion": summary["contextVersion"],
            "analysisId": summary["analysisId"],
            "planningPackId": generated["planningPackId"],
            "estimateId": estimate["estimateId"],
            "status": preview["validation"]["status"],
            "approvalRequired": True,
            "requirementSummary": summary,
            "engineeringEstimation": estimate,
            "planningPreview": preview,
            "context": generated.get("context") or {},
            "correlationId": summary["correlationId"],
            "generatedAt": _now(),
            "_artifact": artifact,
        }
        values = self.store.read()
        values[requirement_id] = record
        self.store.write(values)
        self._publish(record)
        return _public(record)

    def preview(self, request: dict[str, Any]) -> dict[str, Any]:
        requirement_id = _text(request.get("requirementId"))
        planning_pack_id = _text(request.get("planningPackId"))
        records = [value for value in self.store.read().values() if isinstance(value, dict)]
        record = next((item for item in records if requirement_id and item.get("requirementId") == requirement_id), None)
        if record is None:
            record = next((item for item in records if planning_pack_id and item.get("planningPackId") == planning_pack_id), None)
        if record is None:
            raise LookupError("Generate a Planning Pack from an approved Requirement Summary before requesting its preview.")
        summary = self._approved_summary(str(record.get("requirementId") or ""))
        if record.get("requirementContextVersion") != summary["contextVersion"] or record.get("analysisId") != summary["analysisId"]:
            raise ValueError("Planning Preview is stale because the Requirement Summary changed. Generate it again.")
        return {
            "requirementId": record["requirementId"],
            "planningPackId": record["planningPackId"],
            "estimateId": record["estimateId"],
            "status": record["status"],
            "approvalRequired": True,
            "requirementSummary": record["requirementSummary"],
            "engineeringEstimation": record["engineeringEstimation"],
            "planningPreview": record["planningPreview"],
            "correlationId": record["correlationId"],
        }

    def _approved_summary(self, requirement_id: str) -> dict[str, Any]:
        requirement = self.requirement_ingestion.get(requirement_id)
        if not requirement:
            raise LookupError("Requirement Context was not found. Start with Requirement Ingestion.")
        analysis = self.requirement_analysis.assert_approved(requirement_id)
        summary = build_requirement_summary(requirement, analysis)
        repository_suggestion = analysis.get("repositorySuggestion") or {}
        selected = repository_suggestion.get("suggestedRepository") or {}
        repository_id = _text(summary.get("repository", {}).get("repositoryId"))
        if selected and repository_id and repository_id != _text(selected.get("repositoryId")):
            raise ValueError("Approved repository mapping no longer matches Repository Detection. Re-analyze the requirement.")
        return summary

    def _repository_context(self, summary: dict[str, Any]) -> dict[str, Any]:
        repository = summary["repository"]
        repository_id = _text(repository.get("repositoryId"))
        if not repository_id or not self.repository_intelligence:
            return {"mode": "Unavailable", "repositoryId": repository_id, "warnings": ["Repository context is unavailable."]}
        snapshot = self.repository_intelligence.get_current_snapshot(repository_id) or {}
        return {
            "mode": "CodeIndexed" if snapshot else "Unavailable",
            "repositoryId": repository_id,
            "repositoryName": repository.get("name"),
            "branch": repository.get("branch"),
            "snapshotId": snapshot.get("snapshotId"),
            "repositorySnapshotVersion": snapshot.get("version"),
            "modules": list(snapshot.get("modules") or []),
            "languages": dict(snapshot.get("languages") or {}),
            "totalFiles": int(snapshot.get("totalFiles") or 0),
            "warnings": [] if snapshot else ["The selected repository has no completed snapshot."],
        }

    def _artifact(self, planning_pack_id: str) -> dict[str, Any]:
        artifacts = list((self.artifact_provider() or {}).get("artifacts") or [])
        artifact = next((item for item in artifacts if item.get("artifact_id") == planning_pack_id), None)
        if not artifact:
            raise LookupError("Generated Planning Pack artifact could not be loaded.")
        return dict(artifact)

    @staticmethod
    def _preview(summary: dict[str, Any], generated: dict[str, Any], artifact: dict[str, Any], estimate: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
        effective = dict(estimate.get("effectiveEstimate") or {})
        context = generated.get("context") or {}
        blockers = list(summary.get("planningReadiness", {}).get("blockers") or []) + list(context.get("blockers") or [])
        warnings = list(summary.get("planningReadiness", {}).get("warnings") or []) + list(context.get("warnings") or []) + list(repository.get("warnings") or [])
        return {
            "title": summary["title"],
            "source": "RequirementSummary",
            "planningPackVersion": artifact.get("version", 1),
            "repository": summary["repository"],
            "hierarchy": dict((artifact.get("payload") or {}).get("recommendedHierarchy") or {}),
            "estimationReport": dict(effective.get("report") or {}),
            "topEstimationDrivers": list(effective.get("topEstimationDrivers") or []),
            "validation": {
                "status": "Blocked" if blockers else "NeedsReview" if warnings else "ReadyForApproval",
                "blockers": blockers,
                "warnings": warnings,
                "requirementQualityScore": summary.get("qualityScore", 0),
                "requirementConfidence": summary.get("confidence", 0),
                "repositoryMode": repository.get("mode"),
            },
            "recommendedAction": "Resolve Planning blockers" if blockers else "Review and approve Planning Pack",
        }

    def _publish(self, record: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": "RequirementPlanningPreviewCreated",
            "source": "PlanningIntelligence",
            "projectId": record["requirementSummary"].get("projectId"),
            "correlationId": record.get("correlationId"),
            "payload": {
                "requirementId": record.get("requirementId"),
                "planningPackId": record.get("planningPackId"),
                "estimateId": record.get("estimateId"),
                "status": record.get("status"),
            },
        })


def _required_requirement_id(request: dict[str, Any]) -> str:
    requirement_id = _text(request.get("requirementId") or request.get("requirementContextId"))
    if not requirement_id:
        raise ValueError("requirementId is required. Raw planning input cannot bypass Requirement Intelligence.")
    return requirement_id


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
