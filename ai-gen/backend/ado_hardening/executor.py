"""Phase 6 service adapter used by the Azure DevOps hardening harness."""

from __future__ import annotations

from typing import Any


class AzureDevOpsPhase6Executor:
    is_mock = False

    def __init__(self, *, azure_devops, intelligence, automation, agent, platform) -> None:
        self.azure_devops = azure_devops
        self.intelligence = intelligence
        self.automation = automation
        self.agent = agent
        self.platform = platform

    def execute(self, scenario_id: str, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        handlers = {
            "manual-requirement-hierarchy": self._hierarchy,
            "existing-epic-analysis": self._epic,
            "existing-story-estimation": self._story,
            "pull-request-approved-comment": self._pull_request,
            "stale-work-item-recommendation": self._stale,
            "sprint-burndown-risk": self._sprint,
            "build-failure-agent-response": self._build_failure,
            "duplicate-webhook-idempotency": self._duplicate_webhook,
            "permission-loss-safe-failure": self._permission_loss,
            "azure-devops-outage-recovery": self._outage,
        }
        return handlers[scenario_id](request, correlation_id)

    def security_probe(self, request: dict[str, Any]) -> dict[str, Any]:
        from backend.ado_agent.api import build_ado_agent_router
        from backend.integrations.azure_devops.automation.api import build_ado_automation_router
        from backend.integrations.azure_devops.infrastructure.client import AzureDevOpsReadClient

        automation_routes = {route.path for route in build_ado_automation_router(self.automation).routes}
        agent_routes = {route.path for route in build_ado_agent_router(self.agent).routes}
        connection_values = self.azure_devops.connections.list()
        serialized = repr(connection_values).lower()
        forbidden_read_methods = {"create_work_item", "update_work_item", "delete_work_item", "create_pull_request", "merge_pull_request"}
        expected_automation = {
            "/ado-automation/planning-packs/{planning_pack_id}/preview",
            "/ado-automation/planning-packs/{planning_pack_id}/apply",
            "/ado-automation/recommendations/{recommendation_id}/preview",
            "/ado-automation/recommendations/{recommendation_id}/apply",
        }
        checks = [
            _check("credentials_protected", not any(key in serialized for key in ("pat\'", "token\'", "password\'", "secretreference")), "Connection APIs expose no credential or secret-reference values."),
            _check("read_write_separated", forbidden_read_methods.isdisjoint(set(dir(AzureDevOpsReadClient))), "Read client exposes no mutation methods."),
            _check("no_arbitrary_patch_api", automation_routes == expected_automation, "Automation API is restricted to approved planning packs and recommendations."),
            _check("agent_has_no_merge_route", all("merge" not in path.lower() for path in agent_routes), "Agent API exposes no PR approval or merge operation."),
        ]
        return {"passed": all(item["passed"] for item in checks), "checks": checks}

    def _hierarchy(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        pack_id = _required(request, "planningPackId")
        payload = self._automation_request(request, correlation_id)
        preview = self.automation.preview_planning_pack(pack_id, payload, correlation_id=correlation_id)
        applied = None
        if request.get("allowWrites"):
            applied = self.automation.apply_planning_pack(pack_id, payload, correlation_id=correlation_id)
        passed = bool(preview.get("dryRun")) and (applied is None or applied.get("status") == "Completed")
        return _result(passed, "Planning Pack previewed and applied only when live test writes were approved.", operations=["hierarchy_creation_preview", "hierarchy_application"], preview=preview, applied=applied)

    def _epic(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        value = self.intelligence.analyze(_required(request, "epicWorkItemId"), {"projectId": _required(request, "projectId")}, correlation_id=correlation_id)
        return _result(bool(value.get("recommendations")), "Epic quality and decomposition recommendations generated.", operations=["work_item_analysis"], analysis=value)

    def _story(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        work_item_id = _required(request, "storyWorkItemId")
        payload = {"projectId": _required(request, "projectId"), "teamId": str(request.get("teamId") or "")}
        analysis = self.intelligence.analyze(work_item_id, payload, correlation_id=correlation_id)
        estimate = self.intelligence.estimation.estimate(work_item_id, payload, correlation_id=correlation_id)
        return _result(bool(analysis) and bool(estimate), "Story decomposition and explainable estimate generated.", operations=["work_item_analysis", "estimation"], analysis=analysis, estimate=estimate)

    def _pull_request(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        pull_request_id = _required(request, "pullRequestId")
        payload = {"projectId": _required(request, "projectId"), "connectionId": _required(request, "connectionId"), "repositoryId": _required(request, "repositoryId")}
        report = self.intelligence.pull_requests.analyze(pull_request_id, payload, correlation_id=correlation_id)
        preview = self.intelligence.pull_requests.preview_comment(pull_request_id, payload)
        posted = None
        if request.get("allowWrites"):
            posted = self.intelligence.pull_requests.post_approved_comment(pull_request_id, {**payload, "commentPreviewId": preview["commentPreviewId"], "approved": True, "approvedBy": str(request.get("approver") or "phase6-test-approver"), "idempotencyKey": f"{correlation_id}-pr-comment", "reason": "Phase 6.9 isolated test-project validation."}, correlation_id=correlation_id)
        return _result(bool(report) and bool(preview) and (posted is None or posted.get("posted") is True), "PR intelligence completed and comment remained approval-gated.", operations=["pr_analysis"], report=report, preview=preview, posted=posted)

    def _stale(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        recommendation_id = _required(request, "staleRecommendationId")
        try:
            self.intelligence.regenerate(recommendation_id, {"projectId": _required(request, "projectId")}, correlation_id=correlation_id)
        except Exception as error:
            stale = "stale" in str(error).lower()
            return _result(stale, "Changed source revision invalidated the approved recommendation.", operations=["work_item_analysis"], errorType=type(error).__name__)
        return _result(False, "The configured recommendation did not become stale after the source revision changed.", operations=["work_item_analysis"])

    def _sprint(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        value = self.intelligence.sprints.report(_required(request, "projectId"), _required(request, "iterationId"), team_id=str(request.get("teamId") or ""))
        return _result(bool(value.get("burndownSeries")) and isinstance(value.get("deliveryRisks"), list), "Sprint burndown and risk report generated from synchronized ADO data.", operations=["sprint_report"], report=value)

    def _build_failure(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        value = self.agent.prepare("BuildFailed", {"connectionId": _required(request, "connectionId"), "projectId": _required(request, "projectId"), "buildId": str(request.get("buildId") or "phase6-build")}, correlation_id=correlation_id)
        return _result(bool(value.get("packId")), "Build failure produced an auditable agent response without autonomous writes.", operations=["agent_response"], actionPack=value)

    def _duplicate_webhook(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        payload = {"eventId": f"{correlation_id}-duplicate", "eventType": "workitem.updated", "connectionId": _required(request, "connectionId"), "projectId": _required(request, "projectId"), "resource": {"id": int(request.get("storyWorkItemId") or request.get("epicWorkItemId") or 0)}}
        first = self.azure_devops.sync.receive_webhook(payload, correlation_id=correlation_id)
        second = self.azure_devops.sync.receive_webhook(payload, correlation_id=correlation_id)
        return _result(first.get("duplicate") is False and second.get("duplicate") is True, "Duplicate service-hook delivery was accepted idempotently once.", operations=["incremental_sync"], first=first, second=second)

    def _permission_loss(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        recommendation_id = _required(request, "permissionRecommendationId")
        try:
            self.automation.preview_recommendation(recommendation_id, self._automation_request(request, correlation_id), correlation_id=correlation_id)
        except Exception as error:
            denied = "permission" in str(error).lower() or "write" in str(error).lower()
            return _result(denied, "Permission loss failed safely before any Azure DevOps write.", operations=["hierarchy_creation_preview"], errorType=type(error).__name__)
        return _result(False, "Permission-loss fixture unexpectedly passed automation preview.", operations=["hierarchy_creation_preview"])

    def _outage(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        value = self.azure_devops.connections.validate(str(request.get("outageConnectionId") or _required(request, "connectionId")), correlation_id=correlation_id)
        failed_safely = value.get("status") == "Failed" and bool(value.get("validationMessage"))
        return _result(failed_safely, "Azure DevOps outage exhausted bounded retries and produced a recoverable health result.", operations=["initial_sync"], connection=value)

    @staticmethod
    def _automation_request(request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return {"connectionId": _required(request, "connectionId"), "projectId": _required(request, "projectId"), "idempotencyKey": f"{correlation_id}-apply", "executor": str(request.get("executor") or "phase6-test-executor"), "reason": "Phase 6.9 isolated test-project validation."}


def _required(request: dict[str, Any], key: str) -> str:
    value = str(request.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required for this hardening scenario.")
    return value


def _check(check_id: str, passed: bool, details: str) -> dict[str, Any]:
    return {"checkId": check_id, "passed": bool(passed), "details": details}


def _result(passed: bool, details: str, *, operations: list[str], **evidence: Any) -> dict[str, Any]:
    return {"passed": bool(passed), "details": details, "operations": operations, "evidence": evidence}
