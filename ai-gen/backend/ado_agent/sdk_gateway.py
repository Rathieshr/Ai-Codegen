"""Server-side adapter to HEI Platform SDK service contracts.

The public TypeScript SDK uses the same operations. This adapter prevents the
agent from reaching into transports or Azure DevOps clients directly.
"""

from __future__ import annotations

from typing import Any

from backend.platform_sdk import as_azure_devops_sdk


class HEIPlatformSdkAdapter:
    def __init__(self, *, intelligence: Any, automation: Any, azure_devops: Any, planning_pack_provider) -> None:
        self.intelligence = intelligence
        self.automation = automation
        self.azure_devops = as_azure_devops_sdk(azure_devops)
        self.planning_pack_provider = planning_pack_provider

    def analyze_work_item(self, work_item_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.analyze(work_item_id, payload, correlation_id=correlation_id)

    def estimate_work_item(self, work_item_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.estimation.handle(work_item_id, payload, correlation_id=correlation_id)

    def analyze_pull_request(self, pull_request_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.pull_requests.analyze(pull_request_id, payload, correlation_id=correlation_id)

    def preview_pull_request_comment(self, pull_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.intelligence.pull_requests.preview_comment(pull_request_id, payload)

    def sprint_report(self, project_id: str, iteration_id: str, team_id: str = "") -> dict[str, Any]:
        if not iteration_id:
            return self.intelligence.sprints.current(project_id, team_id)
        return self.intelligence.sprints.report(project_id, iteration_id, team_id=team_id)

    def reconcile(self, connection_id: str, project_id: str, correlation_id: str) -> dict[str, Any]:
        return self.azure_devops.request_reconciliation(connection_id, project_id, correlation_id=correlation_id)

    def preview_planning_pack(self, pack_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.automation.preview_planning_pack(pack_id, payload, correlation_id=correlation_id)

    def preview_recommendation(self, recommendation_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.automation.preview_recommendation(recommendation_id, payload, correlation_id=correlation_id)

    def apply(self, operation: str, source_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        if operation == "ApplyPlanningPack":
            return self.automation.apply_planning_pack(source_id, payload, correlation_id=correlation_id)
        if operation == "ApplyRecommendation":
            return self.automation.apply_recommendation(source_id, payload, correlation_id=correlation_id)
        if operation == "PostPullRequestComment":
            return self.intelligence.pull_requests.post_approved_comment(source_id, payload, correlation_id=correlation_id)
        raise ValueError(f"Unsupported approved Azure DevOps agent operation: {operation}.")

    def current_revision(self, entity: dict[str, Any], project_id: str) -> str:
        kind = str(entity.get("type") or "")
        entity_id = str(entity.get("id") or "")
        if kind == "WorkItem":
            found = self.azure_devops.find_cached("workItems", entity_id, project_id)
            return str((found or ({}, {}))[1].get("revision") or "") if found else ""
        if kind == "PlanningPack":
            pack = self.planning_pack_provider(entity_id) or {}
            return str(pack.get("version") or "")
        if kind == "Recommendation":
            recommendation = self.intelligence.repository.get(entity_id)
            if not recommendation:
                return ""
            found = self.azure_devops.find_cached("workItems", str(recommendation.work_item_id), project_id)
            return str((found or ({}, {}))[1].get("revision") or "") if found else ""
        if kind == "PullRequest":
            found = self.azure_devops.find_cached("pullRequests", entity_id, project_id)
            value = (found or ({}, {}))[1] if found else {}
            return str(value.get("revision") or value.get("lastMergeSourceCommit") or value.get("sourceCommitId") or "")
        return str(entity.get("revision") or "")
