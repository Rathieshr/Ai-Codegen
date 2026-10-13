"""Shared orchestration for HEI's project-first and work-item-first entry points."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from backend.platform.shared import JsonMapStore

from .models import EngineeringEntryMode


class EngineeringContextNotFoundError(LookupError):
    pass


class HEIIntelligenceOrchestrator:
    """Combines mature intelligence outputs into one persisted context contract."""

    def __init__(
        self,
        store: JsonMapStore,
        *,
        engineering_intelligence: Any,
        work_item_intelligence: Any | None = None,
        acceptance_criteria: Any | None = None,
    ) -> None:
        self._store = store
        self._engineering = engineering_intelligence
        self._work_items = work_item_intelligence
        self._acceptance = acceptance_criteria
        self._lock = RLock()

    def build_context(self, request: dict[str, Any]) -> dict[str, Any]:
        mode = str(request.get("entryMode") or EngineeringEntryMode.REQUIREMENT).upper()
        if mode not in EngineeringEntryMode.ALL:
            raise ValueError(f"Unsupported Engineering Intelligence entry mode: {mode}")
        correlation_id = str(request.get("correlationId") or f"corr-{uuid4().hex[:16]}")
        project_id = str(request.get("projectId") or "")
        repository_id = str(request.get("repositoryId") or "")
        work_item_id = str(request.get("workItemId") or "")
        work_item_context: dict[str, Any] = {}

        if mode == EngineeringEntryMode.WORK_ITEM:
            if not work_item_id:
                raise ValueError("WORK_ITEM mode requires workItemId.")
            if not self._work_items:
                raise ValueError("Work Item Intelligence is not configured.")
            work_item_context = self._work_items.build_work_item_context(
                work_item_id,
                project_id,
                analyze=bool(request.get("analyzeWorkItem", True)),
                repository_id=repository_id,
                correlation_id=correlation_id,
            )
            if not work_item_context.get("available"):
                raise EngineeringContextNotFoundError(f"Work item {work_item_id} was not found.")
            requirement = _requirement_from_work_item(work_item_context, repository_id)
        else:
            requirement = _requirement_input(request, repository_id)

        result = self._engineering.generate_planning_context(
            requirement, correlation_id=correlation_id,
        )
        context = dict(result.get("engineeringContext") or {})
        related = _related_work_items(context)
        related_intelligence = self._related_intelligence(
            related, project_id, current_id=work_item_id,
        )
        evidence = _collect_evidence(context, work_item_context, related_intelligence)
        rejected = _collect_rejected(context)
        now = datetime.now(timezone.utc).isoformat()
        context.update({
            "entryMode": mode,
            "project": {
                "projectId": project_id or (context.get("azureDevOps") or {}).get("projectId") or "",
                "projectName": str(request.get("projectName") or ""),
            },
            "workItem": dict(work_item_context.get("workItem") or {}),
            "workItemIntelligence": _without_rejected(work_item_context),
            "relatedWorkItems": related,
            "relatedWorkItemIntelligence": related_intelligence,
            "conflicts": list((context.get("repository_markdown_context") or {}).get("conflicts") or []),
            "unknowns": _unknowns(context, work_item_context),
            "evidence": evidence,
            "provenance": [_provenance(item, context, now) for item in evidence],
            "lineage": {
                "projectId": project_id,
                "repositoryId": repository_id or (context.get("repository") or {}).get("repositoryId") or "",
                "workItemId": work_item_id,
                "requirementId": str(requirement.get("requirementId") or ""),
                "planningProposalId": str(request.get("planningProposalId") or ""),
                "engineeringContextId": context.get("contextId"),
                "analysisVersion": str((work_item_context.get("analysis") or {}).get("analysisId") or requirement.get("analysisId") or ""),
                "knowledgeVersion": str((context.get("sourceVersions") or {}).get("projectKnowledgeVersion") or ""),
                "rejectedContext": rejected,
            },
        })
        context["promptContext"] = _prompt_context(context)
        result["engineeringContext"] = context
        result["entryMode"] = mode
        result["crossNavigation"] = _cross_navigation(context)
        self._save(context)
        return result

    def analyze_work_item(self, work_item_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return self.build_context({
            **request,
            "entryMode": EngineeringEntryMode.WORK_ITEM,
            "workItemId": str(work_item_id),
            "analyzeWorkItem": True,
        })

    def generate_acceptance_criteria(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self._acceptance:
            raise ValueError("The stabilized Acceptance Criteria provider is not configured.")
        requirement = dict(request.get("requirement") or {})
        return self._acceptance.generate(
            requirement,
            dict(request.get("projectProfile") or {}),
            options=dict(request.get("options") or {}),
        )

    def get_context(self, context_id: str) -> dict[str, Any]:
        context = self._store.read().get(str(context_id))
        if not isinstance(context, dict):
            raise EngineeringContextNotFoundError(str(context_id))
        return context

    def _related_intelligence(
        self, related: list[dict[str, Any]], project_id: str, *, current_id: str,
    ) -> list[dict[str, Any]]:
        if not self._work_items:
            return []
        values: list[dict[str, Any]] = []
        seen = {str(current_id)} if current_id else set()
        for match in related[:10]:
            item_id = str(match.get("id") or match.get("workItemId") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            context = self._work_items.build_work_item_context(
                item_id, project_id, analyze=False,
            )
            if context.get("available"):
                values.append(_without_rejected(context))
        return values

    def _save(self, context: dict[str, Any]) -> None:
        with self._lock:
            values = self._store.read()
            values[str(context["contextId"])] = context
            self._store.write(values)


def _requirement_input(request: dict[str, Any], repository_id: str) -> dict[str, Any]:
    requirement = dict(request.get("requirement") or {})
    requirement.setdefault("projectId", request.get("projectId"))
    requirement.setdefault("projectName", request.get("projectName"))
    requirement.setdefault("repositoryId", repository_id)
    return requirement


def _requirement_from_work_item(context: dict[str, Any], repository_id: str) -> dict[str, Any]:
    item = context.get("workItem") or {}
    analysis = context.get("analysis") or {}
    return {
        "requirementId": f"work-item-{item.get('workItemId') or item.get('id')}",
        "title": item.get("title"),
        "planningRequirement": item.get("description") or item.get("title"),
        "businessGoals": [analysis.get("businessGoal")] if analysis.get("businessGoal") else [],
        "functionalRequirements": [item.get("description")] if item.get("description") else [],
        "acceptanceCriteria": item.get("acceptanceCriteria") or [],
        "dependencies": analysis.get("dependencies") or [],
        "risks": analysis.get("risk") or [],
        "projectId": item.get("projectId"),
        "repositoryId": repository_id,
        "workItemId": item.get("workItemId") or item.get("id"),
        "workItemType": item.get("workItemType"),
        "analysisId": analysis.get("analysisId"),
        "contextVersion": item.get("revision"),
    }


def _related_work_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in (context.get("similarWork") or {}).get("matches") or []:
        item = dict(match.get("workItem") or match)
        item_id = str(item.get("id") or item.get("workItemId") or "")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        values.append({**item, "confidence": match.get("confidence"), "reason": match.get("reason")})
    return values


def _collect_evidence(
    context: dict[str, Any], work_item: dict[str, Any], related: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    values.extend(item for item in context.get("relevantDocumentation") or [] if isinstance(item, dict))
    values.extend(item for item in (context.get("architecture") or {}).get("evidence") or [] if isinstance(item, dict))
    values.extend(item for item in (context.get("projectIntelligence") or {}).get("approvedArtifacts") or [] if isinstance(item, dict))
    values.extend(item for item in (work_item.get("analysis") or {}).get("evidence") or [] if isinstance(item, dict))
    for item in related:
        work = item.get("workItem") or {}
        values.append({
            "sourceType": "WorkItemIntelligence",
            "sourceId": work.get("workItemId") or work.get("id"),
            "title": work.get("title"),
            "confidence": (item.get("analysis") or {}).get("confidence") or 0,
        })
    return _unique(values)[:80]


def _collect_rejected(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *list((context.get("projectIntelligence") or {}).get("rejectedContext") or []),
        *list((context.get("repository_markdown_context") or {}).get("rejected") or []),
    ]


def _provenance(item: dict[str, Any], context: dict[str, Any], timestamp: str) -> dict[str, Any]:
    repository = context.get("repository") or {}
    project = context.get("project") or {}
    return {
        "classification": item.get("classification") or "EVIDENCE",
        "sourceType": item.get("sourceType") or item.get("source") or "EngineeringIntelligence",
        "sourceId": str(item.get("sourceId") or item.get("evidenceId") or item.get("id") or ""),
        "projectId": str(item.get("projectId") or project.get("projectId") or ""),
        "repositoryId": str(item.get("repositoryId") or repository.get("repositoryId") or ""),
        "workItemId": str(item.get("workItemId") or ""),
        "filePath": str(item.get("path") or item.get("filePath") or ""),
        "section": str(item.get("heading") or item.get("section") or ""),
        "provider": str(item.get("provider") or ""),
        "model": str(item.get("model") or ""),
        "promptVersion": str(item.get("promptVersion") or ""),
        "confidence": float(item.get("confidence") or 0),
        "repositoryRevision": str(item.get("repositoryRevision") or repository.get("repositorySnapshotVersion") or ""),
        "knowledgeVersion": str((context.get("sourceVersions") or {}).get("projectKnowledgeVersion") or ""),
        "timestamp": str(item.get("timestamp") or timestamp),
    }


def _unknowns(context: dict[str, Any], work_item: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    if not (context.get("repository") or {}).get("repositoryId"):
        values.append({"name": "Repository", "reason": "No repository was selected."})
    if work_item and not (work_item.get("analysis") or {}).get("analysisId"):
        values.append({"name": "Work Item Analysis", "reason": "No prior analysis was available."})
    return values


def _without_rejected(value: Any) -> Any:
    if isinstance(value, list):
        return [_without_rejected(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _without_rejected(item)
        for key, item in value.items()
        if key not in {"rejectedContext", "rejected", "rawContext"}
    }


def _prompt_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "contextId", "contextVersion", "entryMode", "requirement", "project",
        "workItem", "repository", "relevantDocumentation", "architecture",
        "dependencies", "similarWork", "relatedWorkItems", "engineeringMemory",
        "projectIntelligence", "workItemIntelligence", "impact", "reuse",
        "readiness", "evidence", "provenance", "sourceVersions", "correlationId",
    }
    return _without_rejected({key: context[key] for key in allowed if key in context})


def _cross_navigation(context: dict[str, Any]) -> dict[str, Any]:
    work_item_id = str((context.get("workItem") or {}).get("workItemId") or "")
    query = f"?view=planning&workItemId={work_item_id}" if work_item_id else "?view=planning"
    return {
        "openInPlanning": query,
        "openRelatedWorkItems": [
            {"workItemId": item.get("id") or item.get("workItemId"), "title": item.get("title")}
            for item in context.get("relatedWorkItems") or []
        ],
    }


def _unique(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        marker = str(item.get("evidenceId") or item.get("sourceId") or item.get("id") or item.get("path") or item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result
