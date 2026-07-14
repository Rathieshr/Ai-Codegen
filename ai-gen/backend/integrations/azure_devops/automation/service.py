"""Approval-gated Azure DevOps work-item automation service."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

from backend.ado_intelligence.models import RecommendationStatus

from .compiler import AutomationCommandCompiler
from .models import (
    AddWorkItemCommentCommand,
    AutomationCommand,
    AutomationPlan,
    CREATE_COMMANDS,
    LinkParentChildCommand,
)


class AutomationNotFoundError(LookupError):
    pass


class AutomationApprovalError(PermissionError):
    pass


class AutomationPermissionError(PermissionError):
    pass


class AutomationConflictError(RuntimeError):
    pass


class AutomationValidationError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AzureDevOpsAutomationService:
    """Compiles approved sources and applies only the fixed command allow-list."""

    WRITE_PERMISSION = "WorkItems.Write"
    _WRITE_ALIASES = {
        "workitems.write", "vso.work_write", "edit work items in this node",
        "edit work items", "project administrators", "contributors",
    }

    def __init__(
        self,
        *,
        azure_devops,
        recommendations,
        execution_store,
        planning_pack_provider: Callable[[str], dict[str, Any] | None],
        platform=None,
        compiler: AutomationCommandCompiler | None = None,
    ) -> None:
        self.azure_devops = azure_devops
        self.recommendations = recommendations
        self.execution_store = execution_store
        self.planning_pack_provider = planning_pack_provider
        self.platform = platform
        self.compiler = compiler or AutomationCommandCompiler()

    def preview_recommendation(self, recommendation_id: str, request: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        recommendation = self._approved_recommendation(recommendation_id)
        commands, warnings = self.compiler.from_recommendation(recommendation.to_dict())
        return self._build_plan("Recommendation", recommendation_id, recommendation.work_item_revision, recommendation.approved_by, commands, warnings, request, correlation_id).to_dict()

    def apply_recommendation(self, recommendation_id: str, request: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        recommendation = self._approved_recommendation(recommendation_id, allow_applied=True)
        plan = self._build_plan("Recommendation", recommendation_id, recommendation.work_item_revision, recommendation.approved_by, *self.compiler.from_recommendation(recommendation.to_dict()), request, correlation_id)
        if recommendation.status == RecommendationStatus.APPLIED:
            self._validate_apply_request(request)
            saved = self.execution_store.get(self._execution_key(plan, request))
            if saved and saved.get("status") == "Completed":
                return {**saved, "idempotentReplay": True}
            raise AutomationApprovalError("This recommendation was already applied. Regenerate and approve a new recommendation before another write.")
        result = self._apply(plan, request, correlation_id)
        if result["status"] == "Completed":
            recommendation.status = RecommendationStatus.APPLIED
            self.recommendations.save(recommendation)
        return result

    def preview_planning_pack(self, planning_pack_id: str, request: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        pack = self._approved_planning_pack(planning_pack_id)
        commands, warnings = self.compiler.from_planning_pack(pack)
        return self._build_plan("PlanningPack", planning_pack_id, int(pack.get("version") or 0), str(pack.get("approved_by") or pack.get("approvedBy") or ""), commands, warnings, request, correlation_id).to_dict()

    def apply_planning_pack(self, planning_pack_id: str, request: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        pack = self._approved_planning_pack(planning_pack_id)
        commands, warnings = self.compiler.from_planning_pack(pack)
        plan = self._build_plan("PlanningPack", planning_pack_id, int(pack.get("version") or 0), str(pack.get("approved_by") or pack.get("approvedBy") or ""), commands, warnings, request, correlation_id)
        return self._apply(plan, request, correlation_id)

    def _approved_recommendation(self, recommendation_id: str, *, allow_applied: bool = False):
        recommendation = self.recommendations.get(recommendation_id)
        if not recommendation:
            raise AutomationNotFoundError(f"Recommendation '{recommendation_id}' was not found.")
        allowed = {RecommendationStatus.APPROVED, RecommendationStatus.APPLIED} if allow_applied else {RecommendationStatus.APPROVED}
        if recommendation.status not in allowed or not recommendation.approved_by:
            raise AutomationApprovalError("The recommendation must be explicitly approved before Azure DevOps automation can run.")
        return recommendation

    def _approved_planning_pack(self, planning_pack_id: str) -> dict[str, Any]:
        pack = self.planning_pack_provider(planning_pack_id)
        if not isinstance(pack, dict):
            raise AutomationNotFoundError(f"Planning Pack '{planning_pack_id}' was not found.")
        state = str(pack.get("state") or pack.get("status") or "").lower()
        approver = str(pack.get("approved_by") or pack.get("approvedBy") or "")
        if state not in {"approved", "locked"} or not approver:
            raise AutomationApprovalError("The Planning Pack must be explicitly approved before Azure DevOps automation can run.")
        return pack

    def _build_plan(self, source_type: str, source_id: str, source_revision: int, approved_by: str, commands: list[AutomationCommand], warnings: list[str], request: dict[str, Any], correlation_id: str) -> AutomationPlan:
        connection_id = str(request.get("connectionId") or request.get("connection_id") or "")
        if not connection_id:
            raise AutomationValidationError("connectionId is required.")
        connection = self.azure_devops.connections.get(connection_id)
        if not connection:
            raise AutomationNotFoundError(f"Azure DevOps connection '{connection_id}' was not found.")
        if connection.get("status") != "Connected":
            raise AutomationValidationError("Azure DevOps connection must be validated and Connected before automation can run.")
        project_id = str(request.get("projectId") or request.get("project_id") or connection.get("projectId") or connection.get("projectName") or "")
        if not project_id:
            raise AutomationValidationError("projectId is required.")
        permissions = {str(item).strip().lower() for item in connection.get("permissions") or []}
        has_permission = bool(permissions & self._WRITE_ALIASES)
        conflicts: list[str] = []
        current_values: dict[str, Any] = {}
        client = self.azure_devops.connections.client(connection_id, correlation_id)
        for target in sorted({command.target_ref for command in commands if command.target_ref.isdigit()}):
            current = client.get_work_item(project_id, int(target))
            current_values[target] = _work_item_snapshot(current)
            expected = max((command.expected_revision for command in commands if command.target_ref == target), default=0)
            actual = int(current.get("rev") or 0)
            if expected and actual != expected:
                conflicts.append(f"Work item {target} is now revision {actual}; approved source revision was {expected}. Re-review is required.")
        if not commands:
            warnings.append("The approved source contains no safely mapped Azure DevOps write operations.")
        if not has_permission:
            warnings.append(f"Connection is missing required permission: {self.WRITE_PERMISSION}.")
        plan_id = "ado-plan-" + hashlib.sha256(f"{source_type}:{source_id}:{source_revision}:{connection_id}:{project_id}".encode()).hexdigest()[:16]
        return AutomationPlan(plan_id, source_type, source_id, source_revision, connection_id, project_id, commands, current_values, warnings, conflicts, [self.WRITE_PERMISSION], approved_by, True)

    def _apply(self, plan: AutomationPlan, request: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        self._validate_apply_request(request)
        idempotency_key = str(request.get("idempotencyKey") or request.get("idempotency_key") or "").strip()
        executor = str(request.get("executor") or "").strip()
        reason = str(request.get("reason") or "").strip()
        if plan.conflicts:
            if plan.source_type == "Recommendation":
                recommendation = self.recommendations.get(plan.source_id)
                if recommendation:
                    recommendation.status = RecommendationStatus.STALE
                    self.recommendations.save(recommendation)
            raise AutomationConflictError(" ".join(plan.conflicts))
        connection = self.azure_devops.connections.get(plan.connection_id) or {}
        permissions = {str(item).strip().lower() for item in connection.get("permissions") or []}
        if not permissions & self._WRITE_ALIASES:
            if self.platform and getattr(self.platform, "audit", None):
                self.platform.audit.record({
                    "action": "AzureDevOpsAutomationDenied",
                    "actor": str(request.get("executor") or "unknown"),
                    "source": "API",
                    "targetType": "AzureDevOpsAutomationPlan",
                    "targetId": plan.plan_id,
                    "before": None,
                    "after": {"requiredPermission": self.WRITE_PERMISSION, "sourceType": plan.source_type, "sourceId": plan.source_id},
                    "reason": "Azure DevOps write permission was not available.",
                    "correlationId": correlation_id,
                })
            raise AutomationPermissionError(f"Azure DevOps permission '{self.WRITE_PERMISSION}' is required.")
        if not plan.commands:
            raise AutomationValidationError("The approved source has no safely mapped Azure DevOps write operations.")

        store_key = self._execution_key(plan, request)
        saved = self.execution_store.get(store_key) or {}
        if saved.get("status") == "Completed":
            return {**saved, "idempotentReplay": True}
        completed = set(saved.get("completedCommandIds") or [])
        external_ids = dict(saved.get("externalIds") or {})
        revisions = {str(key): int(value) for key, value in (saved.get("revisions") or {}).items()}
        for target, current in plan.current_values.items():
            revisions.setdefault(str(target), int(current.get("revision") or 0))
        results = list(saved.get("results") or [])
        writer = self.azure_devops.connections.writer(plan.connection_id, correlation_id)
        status = "Completed"
        failure: dict[str, Any] | None = None
        for command in plan.commands:
            if command.command_id in completed:
                continue
            before = self._command_before(command, plan, external_ids)
            proposed = {
                "command": command.to_dict(),
                "resolvedTarget": str(external_ids.get(command.target_ref) or command.target_ref),
                "resolvedParent": str(external_ids.get(command.parent_ref) or command.parent_ref),
            }
            self._audit("AzureDevOpsAutomationAuthorized", executor, plan, command, before, proposed, reason, correlation_id)
            try:
                response = self._execute_command(writer, command, plan.project_id, external_ids, revisions)
                self._capture_result(command, response, external_ids, revisions)
                completed.add(command.command_id)
                result = {"commandId": command.command_id, "commandType": command.TYPE, "status": "Completed", "externalId": self._resolve(command.target_ref, external_ids), "adoRevision": int(response.get("rev") or 0)}
                results.append(result)
                self._audit("AzureDevOpsAutomationApplied", executor, plan, command, before, response, reason, correlation_id)
            except Exception as error:
                status = "Partial" if completed else "Failed"
                failure = {"commandId": command.command_id, "commandType": command.TYPE, "message": str(error)}
                self._audit("AzureDevOpsAutomationFailed", executor, plan, command, before, failure, reason, correlation_id)
                break
        record = {
            "executionId": saved.get("executionId") or f"ado-execution-{hashlib.sha256(store_key.encode()).hexdigest()[:16]}",
            "planId": plan.plan_id, "sourceType": plan.source_type, "sourceId": plan.source_id,
            "status": status, "dryRun": False, "idempotencyKey": idempotency_key,
            "externalIds": external_ids, "revisions": revisions,
            "completedCommandIds": sorted(completed), "results": results,
            "failure": failure, "warnings": plan.warnings, "correlationId": correlation_id,
            "approvedBy": plan.approved_by, "executor": executor,
            "createdAt": saved.get("createdAt") or _now(), "updatedAt": _now(),
            "idempotentReplay": False,
        }
        self.execution_store.save(store_key, record)
        self._publish("AzureDevOpsAutomationCompleted" if status == "Completed" else "AzureDevOpsAutomationFailed", plan, correlation_id, record)
        return record

    @staticmethod
    def _execution_key(plan: AutomationPlan, request: dict[str, Any]) -> str:
        idempotency_key = str(request.get("idempotencyKey") or request.get("idempotency_key") or "").strip()
        return f"{plan.connection_id}:{plan.project_id}:{plan.source_type}:{plan.source_id}:{idempotency_key}"

    @staticmethod
    def _validate_apply_request(request: dict[str, Any]) -> None:
        if not str(request.get("idempotencyKey") or request.get("idempotency_key") or "").strip():
            raise AutomationValidationError("idempotencyKey is required for apply.")
        if not str(request.get("executor") or "").strip():
            raise AutomationValidationError("executor is required for apply.")

    def _execute_command(self, writer, command: AutomationCommand, project: str, external_ids: dict[str, str], revisions: dict[str, int]) -> dict[str, Any]:
        if command.TYPE in {cls.TYPE for cls in CREATE_COMMANDS.values()}:
            return writer.create_work_item(project, command.work_item_type, command.fields)
        target = int(self._resolve(command.target_ref, external_ids))
        expected_revision = revisions.get(str(target)) or command.expected_revision
        if isinstance(command, LinkParentChildCommand):
            parent = int(self._resolve(command.parent_ref, external_ids))
            return writer.link_parent_child(project, parent, target, expected_revision=expected_revision)
        if isinstance(command, AddWorkItemCommentCommand):
            return writer.add_comment(project, target, str(command.fields.get("comment") or ""))
        return writer.update_work_item(project, target, command.fields, expected_revision=expected_revision)

    @staticmethod
    def _resolve(reference: str, external_ids: dict[str, str]) -> str:
        if not reference:
            return ""
        resolved = str(external_ids.get(reference) or reference)
        if not resolved.isdigit():
            raise AutomationConflictError(f"Work-item reference '{reference}' has not been created or mapped.")
        return resolved

    def _capture_result(self, command: AutomationCommand, response: dict[str, Any], external_ids: dict[str, str], revisions: dict[str, int]) -> None:
        external_id = str(response.get("id") or self._resolve(command.target_ref, external_ids))
        if command.TYPE in {cls.TYPE for cls in CREATE_COMMANDS.values()}:
            external_ids[command.target_ref] = external_id
        if external_id:
            revisions[external_id] = int(response.get("rev") or revisions.get(external_id) or command.expected_revision or 1)

    @staticmethod
    def _command_before(command: AutomationCommand, plan: AutomationPlan, external_ids: dict[str, str]) -> Any:
        target = str(external_ids.get(command.target_ref) or command.target_ref)
        return plan.current_values.get(target) or {"externalId": target} if target.isdigit() else None

    def _audit(self, action: str, actor: str, plan: AutomationPlan, command: AutomationCommand, before: Any, after: Any, reason: str, correlation_id: str) -> None:
        if not self.platform or not getattr(self.platform, "audit", None):
            raise AutomationValidationError("Audit service is required for Azure DevOps automation.")
        self.platform.audit.record({
            "action": action, "actor": actor, "source": "API", "targetType": "AzureDevOpsWorkItem",
            "targetId": command.target_ref, "before": before, "after": after,
            "reason": reason or command.reason, "correlationId": correlation_id,
        })

    def _publish(self, event_type: str, plan: AutomationPlan, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "AzureDevOps", "projectId": plan.project_id, "correlationId": correlation_id, "payload": payload})


def _work_item_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    return {"id": value.get("id"), "revision": int(value.get("rev") or 0), "fields": dict(value.get("fields") or {})}
