"""Stable server-side SDK facade for Azure DevOps operational workflows."""

from __future__ import annotations

from typing import Any

from .azure_devops import HEIAzureDevOpsSdk, as_azure_devops_sdk


class HEIPhase6Sdk:
    """The operational validator uses contracts, never ADO transports directly."""

    def __init__(self, *, intelligence: Any, automation: Any, agent: Any, azure_devops: Any, platform: Any) -> None:
        self.intelligence = intelligence
        self.automation = automation
        self.agent = agent
        self.azure_devops: HEIAzureDevOpsSdk = as_azure_devops_sdk(azure_devops)
        self.platform = platform

    def analyze_work_item(self, work_item_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.analyze(work_item_id, payload, correlation_id=correlation_id)

    def approve_recommendation(self, recommendation_id: str, actor: str) -> dict[str, Any]:
        return self.intelligence.approve(recommendation_id, actor)

    def regenerate_recommendation(self, recommendation_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.regenerate(recommendation_id, payload, correlation_id=correlation_id)

    def estimate_work_item(self, work_item_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.estimation.handle(work_item_id, payload, correlation_id=correlation_id)

    def sprint_report(self, project_id: str, iteration_id: str, team_id: str = "") -> dict[str, Any]:
        return self.intelligence.sprints.report(project_id, iteration_id, team_id=team_id)

    def analyze_pull_request(self, pull_request_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.pull_requests.analyze(pull_request_id, payload, correlation_id=correlation_id)

    def preview_pull_request_comment(self, pull_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.intelligence.pull_requests.preview_comment(pull_request_id, payload)

    def post_pull_request_comment(self, pull_request_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.intelligence.pull_requests.post_approved_comment(pull_request_id, payload, correlation_id=correlation_id)

    def preview_planning_pack(self, pack_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.automation.preview_planning_pack(pack_id, payload, correlation_id=correlation_id)

    def apply_planning_pack(self, pack_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.automation.apply_planning_pack(pack_id, payload, correlation_id=correlation_id)

    def preview_recommendation(self, recommendation_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.automation.preview_recommendation(recommendation_id, payload, correlation_id=correlation_id)

    def apply_recommendation(self, recommendation_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.automation.apply_recommendation(recommendation_id, payload, correlation_id=correlation_id)

    def receive_webhook(self, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return self.azure_devops.receive_webhook(payload, correlation_id=correlation_id)

    def reconcile(self, connection_id: str, project_id: str, correlation_id: str) -> dict[str, Any]:
        return self.azure_devops.request_reconciliation(connection_id, project_id, correlation_id=correlation_id)

    def validate_connection(self, connection_id: str, correlation_id: str) -> dict[str, Any]:
        return self.azure_devops.validate_connection(connection_id, correlation_id=correlation_id)

    def run_next_job(self) -> dict[str, Any]:
        return self.platform.job_runner.run_next()

    def audit_by_correlation(self, correlation_id: str) -> dict[str, Any]:
        return self.platform.audit.by_correlation(correlation_id)

    def activity_by_correlation(self, correlation_id: str) -> dict[str, Any]:
        return self.platform.activity.list_recent(limit=500, correlationId=correlation_id)
