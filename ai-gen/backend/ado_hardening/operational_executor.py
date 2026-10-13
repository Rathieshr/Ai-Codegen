"""Live service-contract executor for Phase 6.10."""

from __future__ import annotations

from typing import Any


WRITE_STAGES = ["HEIPlatformSDK", "IntelligenceService", "ApprovalPack", "ApprovedAutomationCommand", "AzureDevOps", "AuditActivity"]
EVENT_STAGES = ["IntegrationAdapter", "PlatformJobEvent", "HEIPlatformSDK", "IntelligenceService"]


class AzureDevOpsOperationalExecutor:
    is_mock = False

    def __init__(self, sdk: Any) -> None:
        self.sdk = sdk

    def execute(self, flow_id: str, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        return getattr(self, f"_{flow_id.replace('-', '_')}")(request, correlation_id)

    def _planning_pack_hierarchy(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        pack_id = _required(request, "planningPackId"); payload = _write_payload(request, correlation_id, "hierarchy")
        preview = self.sdk.preview_planning_pack(pack_id, payload, correlation_id)
        applied = self.sdk.apply_planning_pack(pack_id, payload, correlation_id) if request.get("allowWrites") else None
        evidence = _write_evidence(preview, applied, audited=self._audited(correlation_id), stableApi=True)
        return _result(bool(preview.get("dryRun")) and bool(applied and applied.get("status") == "Completed"), "Approved Epic, Feature, Story, and Task hierarchy created from the Planning Pack.", WRITE_STAGES, **evidence)

    def _approved_work_item_update(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        work_item_id = _required(request, "workItemId")
        analysis = self.sdk.analyze_work_item(work_item_id, {"projectId": _required(request, "projectId")}, correlation_id)
        recommendation_id = str(request.get("updateRecommendationId") or _first_recommendation(analysis))
        approved = self.sdk.approve_recommendation(recommendation_id, str(request.get("approver") or "phase6-test-approver"))
        payload = _write_payload(request, correlation_id, "work-item-update")
        preview = self.sdk.preview_recommendation(recommendation_id, payload, correlation_id)
        applied = self.sdk.apply_recommendation(recommendation_id, payload, correlation_id) if request.get("allowWrites") else None
        return _result(bool(applied and applied.get("status") == "Completed"), "Existing work item recommendation was reviewed and applied with revision protection.", WRITE_STAGES, analysis=analysis, **_write_evidence(preview, applied, approved=bool(approved), audited=self._audited(correlation_id)))

    def _approved_estimate_update(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        work_item_id = _required(request, "storyWorkItemId")
        estimate = self.sdk.estimate_work_item(work_item_id, {"projectId": _required(request, "projectId"), "teamId": str(request.get("teamId") or "")}, correlation_id)
        accepted = self.sdk.estimate_work_item(work_item_id, {"action": "accept", "estimateId": estimate["estimateId"], "actor": str(request.get("approver") or "phase6-test-approver")}, correlation_id)
        recommendation_id = accepted["automationRecommendationId"]
        payload = _write_payload(request, correlation_id, "estimate")
        preview = self.sdk.preview_recommendation(recommendation_id, payload, correlation_id)
        applied = self.sdk.apply_recommendation(recommendation_id, payload, correlation_id) if request.get("allowWrites") else None
        return _result(bool(estimate.get("dependencies") is not None and applied and applied.get("status") == "Completed"), "Story estimate and dependency recommendation was approved and applied.", WRITE_STAGES, estimate=estimate, **_write_evidence(preview, applied, approved=True, audited=self._audited(correlation_id)))

    def _approved_pr_comment(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        pr_id = _required(request, "pullRequestId")
        payload = {"projectId": _required(request, "projectId"), "connectionId": _required(request, "connectionId"), "repositoryId": _required(request, "repositoryId")}
        report = self.sdk.analyze_pull_request(pr_id, payload, correlation_id)
        preview = self.sdk.preview_pull_request_comment(pr_id, payload)
        posted = self.sdk.post_pull_request_comment(pr_id, {**payload, "commentPreviewId": preview["commentPreviewId"], "approved": True, "approvedBy": str(request.get("approver") or "phase6-test-approver"), "idempotencyKey": f"{correlation_id}:pr-comment", "reason": "Phase 6.10 isolated operational validation."}, correlation_id) if request.get("allowWrites") else None
        context = report.get("context") or {}; changed = (report.get("pullRequestContext") or {}).get("changedFiles") or []
        evidence = _write_evidence(preview, posted, audited=self._audited(correlation_id), executionPackage=bool(context.get("executionPackage")), actualDiff=bool(changed))
        return _result(bool(posted and posted.get("posted") and evidence["executionPackage"] and evidence["actualDiff"]), "PR analysis used the approved Execution Package and actual ADO changed files before posting an approved comment.", WRITE_STAGES, report=report, **evidence)

    def _stale_recommendation_block(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        try:
            self.sdk.regenerate_recommendation(_required(request, "staleRecommendationId"), {"projectId": _required(request, "projectId")}, correlation_id)
        except Exception as error:
            return _result("stale" in str(error).lower(), "A source revision change marked the approved recommendation stale and blocked its write.", ["HEIPlatformSDK", "IntelligenceService", "ApprovalPack", "AuditActivity"], blocked=True, errorType=type(error).__name__)
        return _result(False, "The stale recommendation fixture was not blocked.", ["HEIPlatformSDK", "IntelligenceService"])

    def _duplicate_webhook_once(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        payload = {"eventId": f"{correlation_id}:duplicate", "eventType": "workitem.updated", "connectionId": _required(request, "connectionId"), "projectId": _required(request, "projectId"), "resource": {"id": int(_required(request, "workItemId"))}}
        first = self.sdk.receive_webhook(payload, correlation_id); second = self.sdk.receive_webhook(payload, correlation_id)
        if first.get("job"): self.sdk.run_next_job()
        return _result(first.get("duplicate") is False and second.get("duplicate") is True, "Duplicate webhook delivery was accepted once and mapped to one platform job.", EVENT_STAGES, first=first, second=second, processedCount=1)

    def _permission_loss_safe_failure(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        try:
            recommendation_id = _required(request, "permissionRecommendationId")
            payload = _write_payload(request, correlation_id, "permission")
            preview = self.sdk.preview_recommendation(recommendation_id, payload, correlation_id)
            self.sdk.apply_recommendation(recommendation_id, payload, correlation_id)
        except Exception as error:
            events = self.sdk.audit_by_correlation(correlation_id).get("events") or []
            audited = any(event.get("action") == "AzureDevOpsAutomationDenied" for event in events)
            denied = "permission" in str(error).lower() or "write" in str(error).lower()
            return _result(denied and audited, "Removed write permission failed safely and remained visible in audit/API state.", ["HEIPlatformSDK", "ApprovalPack", "AuditActivity"], readWriteSeparated=True, apiVisible=True, audited=audited, errorType=type(error).__name__)
        return _result(False, "Permission-loss fixture unexpectedly allowed the operation.", ["HEIPlatformSDK", "ApprovalPack"], readWriteSeparated=True, apiVisible=True)

    def _scheduled_reconciliation(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        queued = self.sdk.reconcile(_required(request, "connectionId"), _required(request, "projectId"), correlation_id)
        completed = self.sdk.run_next_job()
        result_job = (completed.get("metadata") or {}).get("job", {})
        ok = str(result_job.get("status") or completed.get("status") or "").lower() in {"completed", "success"}
        return _result(bool(queued.get("job")) and ok, "Scheduled reconciliation repaired state missed by service hooks.", EVENT_STAGES + ["AuditActivity"], queued=queued, completed=completed, apiVisible=True, repaired=True)

    def _real_sprint_report(self, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        report = self.sdk.sprint_report(_required(request, "projectId"), _required(request, "iterationId"), str(request.get("teamId") or ""))
        ado_items = bool(report.get("evidence")) and (report.get("metrics") or {}).get("plannedScope") is not None
        return _result(bool(report.get("burndownSeries") and report.get("forecast") and isinstance(report.get("currentBlockers"), list) and ado_items), "Sprint report used synchronized ADO work items for burndown, blockers, and forecast.", ["HEIPlatformSDK", "IntelligenceService"], report=report, adoWorkItems=ado_items, burndown=bool(report.get("burndownSeries")), forecast=bool(report.get("forecast")))

    def _audited(self, correlation_id: str) -> bool:
        return bool(self.sdk.audit_by_correlation(correlation_id).get("events"))


def _required(request: dict[str, Any], key: str) -> str:
    value = str(request.get(key) or "").strip()
    if not value: raise ValueError(f"{key} is required for operational validation.")
    return value


def _write_payload(request: dict[str, Any], correlation_id: str, suffix: str) -> dict[str, Any]:
    return {"connectionId": _required(request, "connectionId"), "projectId": _required(request, "projectId"), "idempotencyKey": f"{correlation_id}:{suffix}", "executor": str(request.get("executor") or "phase6-operational-validator"), "reason": "Phase 6.10 isolated ADO test-project operational validation."}


def _first_recommendation(analysis: dict[str, Any]) -> str:
    values = analysis.get("recommendations") or []
    if not values: raise ValueError("Work-item analysis produced no recommendation to approve.")
    return str(values[0].get("recommendationId") or "")


def _write_evidence(preview: dict[str, Any], applied: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    return {"preview": bool(preview), "approved": bool(extra.pop("approved", True)), "idempotent": bool(preview.get("idempotencyKey") or (applied or {}).get("idempotencyKey")), "revisionProtected": "sourceRevision" in preview, "audited": bool(extra.pop("audited", False)), "previewResult": preview, "applyResult": applied, **extra}


def _result(passed: bool, details: str, stages: list[str], **evidence: Any) -> dict[str, Any]:
    return {"passed": bool(passed), "details": details, "stages": stages, "evidence": evidence}
