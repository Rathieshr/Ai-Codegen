"""Azure DevOps agent orchestration and approval lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .models import ActionPackStatus, AgentTrigger, AzureDevOpsActionPack, now_iso


class ActionPackNotFoundError(LookupError):
    pass


class ActionPackApprovalError(PermissionError):
    pass


class ActionPackConflictError(RuntimeError):
    pass


class ActionPackPolicyError(PermissionError):
    pass


EVENT_TRIGGER_MAP = {
    "RequirementReceived": AgentTrigger.REQUIREMENT_RECEIVED.value,
    "WorkItemCreated": AgentTrigger.REQUIREMENT_RECEIVED.value,
    "PlanningPackApproved": AgentTrigger.PLANNING_PACK_APPROVED.value,
    "WorkItemChanged": AgentTrigger.WORK_ITEM_CHANGED.value,
    "WorkItemUpdated": AgentTrigger.WORK_ITEM_CHANGED.value,
    "AzureDevOpsWorkItemSynchronized": AgentTrigger.WORK_ITEM_CHANGED.value,
    "SprintStarted": AgentTrigger.SPRINT_STARTED.value,
    "SprintNearingEnd": AgentTrigger.SPRINT_NEARING_END.value,
    "PullRequestCreated": AgentTrigger.PULL_REQUEST_CREATED.value,
    "PullRequestUpdated": AgentTrigger.PULL_REQUEST_UPDATED.value,
    "PullRequestMerged": AgentTrigger.PULL_REQUEST_MERGED.value,
    "AzureDevOpsPullRequestSynchronized": AgentTrigger.PULL_REQUEST_UPDATED.value,
    "BuildFailed": AgentTrigger.BUILD_FAILED.value,
    "ScheduledReconciliation": AgentTrigger.SCHEDULED_RECONCILIATION.value,
    "AzureDevOpsReconciliationRequired": AgentTrigger.SCHEDULED_RECONCILIATION.value,
    "ManualRequest": AgentTrigger.MANUAL_REQUEST.value,
}


class AzureDevOpsAgentService:
    def __init__(self, *, repository, sdk, policy, platform, ttl_minutes: int = 60) -> None:
        self.repository = repository
        self.sdk = sdk
        self.policy = policy
        self.platform = platform
        self.ttl_minutes = max(1, ttl_minutes)

    def prepare(self, trigger: str, payload: dict[str, Any], *, correlation_id: str, run_id: str = "") -> dict[str, Any]:
        trigger = EVENT_TRIGGER_MAP.get(trigger, trigger)
        if trigger not in {item.value for item in AgentTrigger}:
            raise ValueError(f"Unsupported Azure DevOps agent trigger: {trigger}.")
        project_id = str(payload.get("projectId") or payload.get("project_id") or "")
        connection_id = str(payload.get("connectionId") or payload.get("connection_id") or "")
        prepared, actions, entities, revisions, risks, warnings = self._prepare(trigger, payload, correlation_id)
        for action in actions:
            action["approvalRequired"] = self.policy.requires_approval(str(action.get("operation") or ""))
            action.setdefault("status", "PendingApproval" if action["approvalRequired"] else "Prepared")
        approval_status = ActionPackStatus.PENDING_APPROVAL.value if any(item["approvalRequired"] for item in actions) else ActionPackStatus.PREPARED.value
        permissions = sorted({permission for action in actions for permission in action.get("requiredPermissions", [])})
        pack = AzureDevOpsActionPack.create(
            trigger=trigger, source_entities=entities, proposed_actions=actions,
            dry_run={"preparedOutputs": prepared, "writesExecuted": False, "operationCount": len(actions)},
            risks=risks, warnings=warnings, required_permissions=permissions,
            approval_status=approval_status,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=self.ttl_minutes)).isoformat(),
            source_revisions=revisions, correlation_id=correlation_id, run_id=run_id,
            project_id=project_id, connection_id=connection_id,
        )
        pack.policy_decision = self.policy.evaluate(pack.to_dict(), operation="prepare")
        if not pack.policy_decision.get("allowed"):
            pack.approval_status = ActionPackStatus.POLICY_DENIED.value
        self.repository.save(pack)
        self._activity("AzureDevOpsActionPackPrepared", pack, "Azure DevOps action pack prepared for review.")
        self._event("AzureDevOpsActionPackPrepared", pack)
        return pack.to_dict()

    def list_runs(self) -> dict[str, Any]:
        values = self.platform.agent_runs.list_recent(200)
        runs = [item for item in values["runs"] if item.get("agentId") == "azure-devops-agent"]
        return {"runs": runs, "count": len(runs)}

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self.platform.agent_runs.get(run_id)
        if not run or run.get("agentId") != "azure-devops-agent":
            raise ActionPackNotFoundError(f"Azure DevOps agent run '{run_id}' was not found.")
        return run

    def list_packs(self) -> dict[str, Any]:
        packs = [self._refresh_state(item).to_dict() for item in self.repository.list()]
        packs.sort(key=lambda value: value.get("createdAt", ""), reverse=True)
        return {"actionPacks": packs, "count": len(packs)}

    def get_pack(self, pack_id: str) -> dict[str, Any]:
        return self._pack(pack_id).to_dict()

    def approve(self, pack_id: str, actor: str, *, reason: str = "") -> dict[str, Any]:
        if not actor.strip():
            raise ActionPackApprovalError("actor is required to approve an Azure DevOps action pack.")
        pack = self._pack(pack_id)
        if pack.approval_status not in {ActionPackStatus.PENDING_APPROVAL.value, ActionPackStatus.PREPARED.value}:
            raise ActionPackApprovalError(f"Action pack cannot be approved from status {pack.approval_status}.")
        self._assert_fresh(pack)
        decision = self.policy.evaluate(pack.to_dict(), operation="approve", actor=actor)
        if not decision.get("allowed"):
            pack.approval_status = ActionPackStatus.POLICY_DENIED.value
            pack.policy_decision = decision
            self.repository.save(pack)
            raise ActionPackPolicyError(self._policy_message(decision))
        before = pack.to_dict()
        pack.approval_status = ActionPackStatus.APPROVED.value
        pack.approved_by = actor
        pack.approved_at = now_iso()
        pack.updated_at = pack.approved_at
        pack.policy_decision = decision
        self.repository.save(pack)
        self._audit("AzureDevOpsActionPackApproved", actor, pack, before, pack.to_dict(), reason)
        self._activity("AzureDevOpsActionPackApproved", pack, "Azure DevOps action pack approved.", actor)
        return pack.to_dict()

    def reject(self, pack_id: str, actor: str, *, reason: str = "") -> dict[str, Any]:
        if not actor.strip():
            raise ActionPackApprovalError("actor is required to reject an Azure DevOps action pack.")
        pack = self._pack(pack_id)
        if pack.approval_status in {ActionPackStatus.APPLIED.value, ActionPackStatus.REJECTED.value}:
            raise ActionPackApprovalError(f"Action pack cannot be rejected from status {pack.approval_status}.")
        before = pack.to_dict()
        pack.approval_status = ActionPackStatus.REJECTED.value
        pack.rejected_by = actor
        pack.rejected_at = now_iso()
        pack.updated_at = pack.rejected_at
        self.repository.save(pack)
        self._audit("AzureDevOpsActionPackRejected", actor, pack, before, pack.to_dict(), reason)
        self._activity("AzureDevOpsActionPackRejected", pack, "Azure DevOps action pack rejected.", actor)
        return pack.to_dict()

    def apply(self, pack_id: str, actor: str, *, reason: str = "", idempotency_key: str = "") -> dict[str, Any]:
        pack = self._pack(pack_id)
        if pack.approval_status == ActionPackStatus.APPLIED.value:
            return {**pack.to_dict(), "idempotentReplay": True}
        if pack.approval_status not in {ActionPackStatus.APPROVED.value, ActionPackStatus.PARTIAL.value, ActionPackStatus.FAILED.value} or not pack.approved_by:
            raise ActionPackApprovalError("The action pack must be explicitly approved before apply.")
        self._assert_fresh(pack)
        decision = self.policy.evaluate(pack.to_dict(), operation="apply", actor=actor)
        if not decision.get("allowed"):
            pack.approval_status = ActionPackStatus.POLICY_DENIED.value
            pack.policy_decision = decision
            self.repository.save(pack)
            raise ActionPackPolicyError(self._policy_message(decision))
        before = pack.to_dict()
        pack.approval_status = ActionPackStatus.APPLYING.value
        pack.updated_at = now_iso()
        self.repository.save(pack)
        results = list(pack.application_results)
        completed_ids = {str(item.get("actionId")) for item in results if item.get("status") == "Completed"}
        failure_count = 0
        for index, action in enumerate(pack.proposed_actions):
            action_id = str(action.get("actionId") or f"action-{index + 1}")
            if action_id in completed_ids or not action.get("approvalRequired"):
                continue
            operation = str(action.get("operation") or "")
            source_id = str(action.get("sourceId") or "")
            request = {
                **dict(action.get("request") or {}),
                "connectionId": pack.connection_id,
                "projectId": pack.project_id,
                "idempotencyKey": idempotency_key or f"{pack.pack_id}:{action_id}",
                "executor": actor,
                "reason": reason or f"Approved Azure DevOps action pack {pack.pack_id}",
                "approved": True,
                "approvedBy": pack.approved_by,
            }
            try:
                result = self.sdk.apply(operation, source_id, request, pack.correlation_id)
                results.append({"actionId": action_id, "operation": operation, "status": "Completed", "result": result})
            except Exception as error:
                failure_count += 1
                results.append({"actionId": action_id, "operation": operation, "status": "Failed", "error": str(error)})
                break
        succeeded = len([item for item in results if item.get("status") == "Completed"])
        pack.application_results = results
        pack.applied_by = actor
        pack.applied_at = now_iso()
        pack.updated_at = pack.applied_at
        if failure_count:
            pack.approval_status = ActionPackStatus.PARTIAL.value if succeeded else ActionPackStatus.FAILED.value
        else:
            pack.approval_status = ActionPackStatus.APPLIED.value
        self.repository.save(pack)
        self._audit("AzureDevOpsActionPackApplied", actor, pack, before, pack.to_dict(), reason)
        self._activity("AzureDevOpsActionPackApplied", pack, f"Azure DevOps action pack apply finished with status {pack.approval_status}.", actor)
        self._event("AzureDevOpsActionPackApplied", pack)
        return {**pack.to_dict(), "idempotentReplay": False}

    def _prepare(self, trigger: str, payload: dict[str, Any], correlation_id: str):
        prepared: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        revisions: dict[str, str] = {}
        risks: list[str] = []
        warnings: list[str] = []
        project = str(payload.get("projectId") or "")
        work_item = str(payload.get("workItemId") or payload.get("requirementId") or "")
        pack_id = str(payload.get("planningPackId") or "")
        recommendation_id = str(payload.get("recommendationId") or "")
        pr_id = str(payload.get("pullRequestId") or "")
        iteration = str(payload.get("iterationId") or "")

        if trigger in {AgentTrigger.REQUIREMENT_RECEIVED.value, AgentTrigger.WORK_ITEM_CHANGED.value} and work_item:
            analysis = self.sdk.analyze_work_item(work_item, payload, correlation_id)
            prepared.append({"type": "RequirementAnalysis", "value": analysis})
            revision = str(analysis.get("workItemRevision") or payload.get("workItemRevision") or "")
            entities.append({"type": "WorkItem", "id": work_item, "revision": revision})
            revisions[f"WorkItem:{work_item}"] = revision
            if trigger == AgentTrigger.WORK_ITEM_CHANGED.value:
                estimate = self.sdk.estimate_work_item(work_item, {**payload, "action": "generate"}, correlation_id)
                prepared.append({"type": "EstimateAndDependencies", "value": estimate})
        elif trigger == AgentTrigger.PLANNING_PACK_APPROVED.value and pack_id:
            preview = self.sdk.preview_planning_pack(pack_id, payload, correlation_id)
            prepared.append({"type": "AzureDevOpsWritePreview", "value": preview})
            revision = str(preview.get("sourceRevision") or payload.get("sourceRevision") or "")
            entities.append({"type": "PlanningPack", "id": pack_id, "revision": revision})
            revisions[f"PlanningPack:{pack_id}"] = revision
            actions.append(self._action("ApplyPlanningPack", pack_id, preview, payload, ["WorkItems.Write"]))
        elif trigger in {AgentTrigger.PULL_REQUEST_CREATED.value, AgentTrigger.PULL_REQUEST_UPDATED.value, AgentTrigger.PULL_REQUEST_MERGED.value} and pr_id:
            report = self.sdk.analyze_pull_request(pr_id, payload, correlation_id)
            prepared.append({"type": "PullRequestIntelligenceReport", "value": report})
            revision = str(payload.get("pullRequestRevision") or report.get("sourceCommitId") or "")
            entities.append({"type": "PullRequest", "id": pr_id, "revision": revision})
            revisions[f"PullRequest:{pr_id}"] = revision
            if trigger != AgentTrigger.PULL_REQUEST_MERGED.value:
                preview = self.sdk.preview_pull_request_comment(pr_id, payload)
                prepared.append({"type": "PullRequestCommentPreview", "value": preview})
                actions.append(self._action("PostPullRequestComment", pr_id, preview, {**payload, "commentPreviewId": preview.get("commentPreviewId")}, ["PullRequests.Comment"]))
        elif trigger in {AgentTrigger.SPRINT_STARTED.value, AgentTrigger.SPRINT_NEARING_END.value, AgentTrigger.BUILD_FAILED.value}:
            report = self.sdk.sprint_report(project, iteration, str(payload.get("teamId") or ""))
            prepared.append({"type": "SprintIntelligenceReport", "value": report})
            entities.append({"type": "Iteration", "id": iteration or str(report.get("iterationId") or "current"), "revision": str(report.get("generatedAt") or "")})
            if trigger == AgentTrigger.BUILD_FAILED.value:
                risks.append("A failed build requires review before further automation.")
        elif trigger == AgentTrigger.SCHEDULED_RECONCILIATION.value:
            prepared.append({"type": "ScheduledReconciliation", "value": self.sdk.reconcile(str(payload.get("connectionId") or ""), project, correlation_id)})
            entities.append({"type": "Project", "id": project, "revision": str(payload.get("syncCursor") or "")})
        elif trigger == AgentTrigger.MANUAL_REQUEST.value:
            prepared, actions, entities, revisions = self._manual(payload, correlation_id)
        else:
            warnings.append("The trigger was accepted but did not contain the identifiers required to prepare intelligence.")

        if recommendation_id:
            preview = self.sdk.preview_recommendation(recommendation_id, payload, correlation_id)
            prepared.append({"type": "AzureDevOpsWritePreview", "value": preview})
            revision = str(preview.get("sourceRevision") or "")
            entities.append({"type": "Recommendation", "id": recommendation_id, "revision": revision})
            revisions[f"Recommendation:{recommendation_id}"] = revision
            actions.append(self._action("ApplyRecommendation", recommendation_id, preview, payload, ["WorkItems.Write"]))
        return prepared, actions, entities, revisions, risks, warnings

    def _manual(self, payload: dict[str, Any], correlation_id: str):
        requested = list(payload.get("requestedActions") or [])
        prepared: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        revisions: dict[str, str] = {}
        for operation in requested:
            name = str(operation)
            if name in self.policy.FORBIDDEN:
                actions.append(self._action(name, "", {}, payload, []))
            elif name == "AnalyzeWorkItem" and payload.get("workItemId"):
                value = self.sdk.analyze_work_item(str(payload["workItemId"]), payload, correlation_id)
                prepared.append({"type": "RequirementAnalysis", "value": value})
            elif name == "EstimateWorkItem" and payload.get("workItemId"):
                value = self.sdk.estimate_work_item(str(payload["workItemId"]), payload, correlation_id)
                prepared.append({"type": "EstimateAndDependencies", "value": value})
        return prepared, actions, entities, revisions

    @staticmethod
    def _action(operation: str, source_id: str, preview: dict[str, Any], request: dict[str, Any], permissions: list[str]) -> dict[str, Any]:
        return {
            "actionId": f"ado-action-{uuid4().hex[:12]}", "operation": operation, "sourceId": source_id,
            "preview": preview, "request": {key: request.get(key) for key in ("connectionId", "projectId", "repositoryId") if request.get(key)},
            "requiredPermissions": permissions,
        }

    def _pack(self, pack_id: str) -> AzureDevOpsActionPack:
        pack = self.repository.get(pack_id)
        if not pack:
            raise ActionPackNotFoundError(f"Azure DevOps action pack '{pack_id}' was not found.")
        return self._refresh_state(pack)

    def _refresh_state(self, pack: AzureDevOpsActionPack) -> AzureDevOpsActionPack:
        if pack.approval_status in {ActionPackStatus.PREPARED.value, ActionPackStatus.PENDING_APPROVAL.value, ActionPackStatus.APPROVED.value}:
            try:
                if datetime.fromisoformat(pack.expires_at) <= datetime.now(timezone.utc):
                    pack.approval_status = ActionPackStatus.EXPIRED.value
                    pack.updated_at = now_iso()
                    self.repository.save(pack)
            except (TypeError, ValueError):
                pass
        return pack

    def _assert_fresh(self, pack: AzureDevOpsActionPack) -> None:
        if pack.approval_status == ActionPackStatus.EXPIRED.value:
            raise ActionPackApprovalError("The Azure DevOps action pack has expired and must be regenerated.")
        stale: list[str] = []
        for entity in pack.source_entities:
            key = f"{entity.get('type')}:{entity.get('id')}"
            expected = str(pack.source_revisions.get(key) or entity.get("revision") or "")
            current = str(self.sdk.current_revision(entity, pack.project_id) or "")
            if expected and current and expected != current:
                stale.append(f"{key} changed from revision {expected} to {current}")
        if stale:
            pack.approval_status = ActionPackStatus.STALE.value
            pack.warnings.extend(stale)
            pack.updated_at = now_iso()
            self.repository.save(pack)
            raise ActionPackConflictError("; ".join(stale))

    @staticmethod
    def _policy_message(decision: dict[str, Any]) -> str:
        return " ".join(str(item.get("message") or "") for item in decision.get("violations") or []) or "Azure DevOps agent policy denied this action."

    def _event(self, event_type: str, pack: AzureDevOpsActionPack) -> None:
        self.platform.events.publish({"eventType": event_type, "source": "Agent", "projectId": pack.project_id, "correlationId": pack.correlation_id, "payload": {"packId": pack.pack_id, "status": pack.approval_status}})

    def _activity(self, activity_type: str, pack: AzureDevOpsActionPack, description: str, actor: str = "") -> None:
        self.platform.activity.add_activity({"activityType": activity_type, "title": "Azure DevOps Agent", "description": description, "source": "Agent", "actor": actor, "projectId": pack.project_id, "correlationId": pack.correlation_id, "metadata": {"packId": pack.pack_id, "trigger": pack.trigger}})

    def _audit(self, action: str, actor: str, pack: AzureDevOpsActionPack, before: dict[str, Any], after: dict[str, Any], reason: str) -> None:
        self.platform.audit.record({"action": action, "actor": actor, "source": "Agent", "targetType": "AzureDevOpsActionPack", "targetId": pack.pack_id, "before": before, "after": after, "reason": reason, "correlationId": pack.correlation_id})


class AzureDevOpsAgent:
    def __init__(self, service: AzureDevOpsAgentService) -> None:
        self.service = service

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        event = dict(context.get("triggerEvent") or {})
        payload = dict(context.get("context") or {})
        return self.service.prepare(str(payload.pop("trigger", "") or event.get("eventType") or ""), payload, correlation_id=str(event.get("correlationId") or payload.get("correlationId") or f"corr-{uuid4().hex[:16]}"))


class AzureDevOpsAgentJobHandler:
    def __init__(self, service: AzureDevOpsAgentService, platform) -> None:
        self.service = service
        self.platform = platform

    def handle(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job.get("payload") or {})
        event = dict(payload.pop("event", {}) or {})
        run = self.platform.agent_runner.run(
            AzureDevOpsAgent(self.service),
            {"agentId": "azure-devops-agent", "name": "Azure DevOps Agent", "enabled": True, "supportedTriggers": sorted(set(EVENT_TRIGGER_MAP.values())), "requiredPermissions": []},
            trigger_event=event, source="Agent", context=payload,
        )
        if run.get("status") == "Failed":
            raise RuntimeError(run.get("error") or "Azure DevOps agent run failed.")
        output = dict(run.get("output") or {})
        event_id = str(event.get("eventId") or "")
        if event_id and output.get("packId"):
            pack = self.service.repository.get(output["packId"])
            if pack:
                pack.run_id = run["runId"]
                pack.updated_at = now_iso()
                self.service.repository.save(pack)
            self.service.repository.complete_event(event_id, run["runId"], output["packId"])
        return {"agentRun": run, "actionPack": output}


class AzureDevOpsAgentEventHandler:
    def __init__(self, repository, platform) -> None:
        self.repository = repository
        self.platform = platform

    def handle(self, event: dict[str, Any]) -> None:
        event_id = str(event.get("eventId") or "")
        if not self.repository.reserve_event(event_id, {"eventType": event.get("eventType"), "correlationId": event.get("correlationId"), "status": "Queued"}):
            return
        event_type = str(event.get("eventType") or "")
        trigger = EVENT_TRIGGER_MAP.get(event_type, event_type)
        if event_type == "AzureDevOpsPullRequestSynchronized" and str((event.get("payload") or {}).get("result") or "").lower() == "created":
            trigger = AgentTrigger.PULL_REQUEST_CREATED.value
        self.platform.jobs.enqueue({"jobType": "AzureDevOpsAgent", "source": "Agent", "correlationId": event.get("correlationId"), "maxRetries": 2, "payload": {**dict(event.get("payload") or {}), "trigger": trigger, "projectId": event.get("projectId") or (event.get("payload") or {}).get("projectId"), "workItemId": event.get("workItemId") or (event.get("payload") or {}).get("workItemId"), "event": event}})
