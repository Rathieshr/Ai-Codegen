"""Requirement Intelligence import for synchronized Azure DevOps work items."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.platform.shared import JsonMapStore
from backend.platform_sdk import as_azure_devops_sdk
from backend.requirement_intake import RequirementIngestionService


SUPPORTED_TYPES = {"epic", "feature", "story", "user story", "task", "bug"}


class ImportedWorkItemNotFoundError(LookupError):
    pass


class UnsupportedWorkItemError(ValueError):
    pass


class AzureDevOpsWorkItemImportService:
    def __init__(self, store: JsonMapStore, *, azure_devops: Any, requirement_ingestion: RequirementIngestionService, platform: Any | None = None) -> None:
        self.store = store
        self.ado_sdk = as_azure_devops_sdk(azure_devops)
        self.requirement_ingestion = requirement_ingestion
        self.platform = platform

    def get(self, work_item_id: str, *, project_id: str = "", connection_id: str = "", refresh: bool = False, correlation_id: str = "") -> dict[str, Any]:
        cached = self.ado_sdk.find_cached("workItems", str(work_item_id), project_id)
        if refresh and connection_id and project_id:
            value = self.ado_sdk.work_item_details(connection_id, project_id, int(work_item_id), correlation_id=correlation_id)
            self.ado_sdk.cache_upsert(project_id, "workItems", str(work_item_id), value)
            cached = (project_id, value)
        if not cached:
            raise ImportedWorkItemNotFoundError(f"Azure DevOps work item {work_item_id} is not available in the synchronized project cache.")
        return self._current(dict(cached[1]), cached[0])

    def analyze(self, work_item_id: str, request: dict[str, Any] | None = None, *, correlation_id: str = "") -> dict[str, Any]:
        request = request or {}
        correlation_id = correlation_id or f"corr-{uuid4().hex[:16]}"
        current = self.get(
            work_item_id,
            project_id=str(request.get("projectId") or ""),
            connection_id=str(request.get("connectionId") or ""),
            refresh=bool(request.get("refresh")),
            correlation_id=correlation_id,
        )
        work_item_type = str(current["workItemType"] or "").strip()
        if work_item_type.casefold() not in SUPPORTED_TYPES:
            raise UnsupportedWorkItemError(f"Work item type '{work_item_type or 'Unknown'}' is not supported for Requirement Intelligence.")
        criteria = current["acceptanceCriteria"]
        missing = _missing_information(current, criteria)
        dependencies = _dependencies(current["linkedWorkItems"])
        ready = not missing
        summary_text = _summary_text(current, criteria, dependencies, missing)
        requirement_context_id = ""
        if ready:
            context = self.requirement_ingestion.ingest({
                "sourceType": "AzureDevOpsWorkItem",
                "workItemId": str(work_item_id),
                "projectId": current["projectId"],
                "projectName": current.get("projectName", ""),
                "repositoryId": str(request.get("repositoryId") or ""),
                "repositoryName": str(request.get("repositoryName") or ""),
                "branch": str(request.get("branch") or ""),
                "actor": str(request.get("actor") or "HEI User"),
                "correlationId": correlation_id,
                "requirementSummary": summary_text,
            })
            requirement_context_id = str(context["requirementId"])
        now = _now()
        result = {
            "analysisId": f"ado-import-{uuid4().hex}",
            "workItemId": str(work_item_id),
            "workItemRevision": current["revision"],
            "status": "Ready" if ready else "NeedsReview",
            "currentWorkItem": current,
            "requirementSummary": {
                "title": current["title"],
                "summary": _summary(current),
                "acceptanceCriteria": criteria,
                "dependencies": dependencies,
                "missingInformation": missing,
                "readyForPlanning": ready,
            },
            "requirementContextId": requirement_context_id,
            "correlationId": correlation_id,
            "generatedAt": now,
        }
        values = self.store.read()
        values[str(work_item_id)] = result
        self.store.write(values)
        self._publish(result)
        return result

    def _current(self, item: dict[str, Any], project_id: str) -> dict[str, Any]:
        links = [_link(value) for value in item.get("links") or [] if isinstance(value, dict)]
        return {
            "workItemId": str(item.get("workItemId") or item.get("id") or ""),
            "workItemType": str(item.get("workItemType") or item.get("type") or ""),
            "title": _clean(item.get("title")),
            "description": _clean(item.get("description")),
            "acceptanceCriteria": _criteria(item.get("acceptanceCriteria")),
            "comments": [_comment(value) for value in item.get("comments") or [] if isinstance(value, dict)],
            "attachments": [_attachment(value) for value in item.get("attachments") or [] if isinstance(value, dict)],
            "linkedWorkItems": links,
            "area": str(item.get("areaPath") or ""),
            "iteration": str(item.get("iterationPath") or ""),
            "tags": [str(value) for value in item.get("tags") or [] if str(value).strip()],
            "state": str(item.get("state") or ""),
            "revision": int(item.get("revision") or 0),
            "projectId": project_id,
            "projectName": str(item.get("projectName") or ""),
        }

    def _publish(self, result: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({
                "eventType": "AzureDevOpsWorkItemImported",
                "source": "RequirementIntelligence",
                "projectId": result["currentWorkItem"]["projectId"],
                "correlationId": result["correlationId"],
                "payload": {"workItemId": result["workItemId"], "status": result["status"], "requirementContextId": result["requirementContextId"]},
            })


def _clean(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>|</(?:p|div|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _criteria(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    return [part.strip(" -") for part in re.split(r"\n+|(?=<li>)", text) if part.strip(" -")]


def _link(value: dict[str, Any]) -> dict[str, Any]:
    relation = str(value.get("relation") or value.get("rel") or "related")
    return {
        "workItemId": str(value.get("targetId") or value.get("target_id") or ""),
        "relationship": relation,
        "url": str(value.get("targetUrl") or value.get("target_url") or ""),
        "isDependency": any(token in relation.casefold() for token in ("dependency", "predecessor", "successor")),
    }


def _comment(value: dict[str, Any]) -> dict[str, Any]:
    return {"commentId": str(value.get("commentId") or value.get("id") or ""), "text": _clean(value.get("text")), "createdBy": str(value.get("createdBy") or ""), "createdAt": str(value.get("createdAt") or "")}


def _attachment(value: dict[str, Any]) -> dict[str, Any]:
    return {"name": str(value.get("name") or "Attachment"), "url": str(value.get("url") or ""), "comment": str(value.get("comment") or "")}


def _missing_information(item: dict[str, Any], criteria: list[str]) -> list[str]:
    missing: list[str] = []
    if not item["title"]:
        missing.append("Title is missing.")
    if len(item["description"]) < 30:
        missing.append("Description does not explain the engineering or business outcome.")
    if item["workItemType"].casefold() in {"feature", "story", "user story", "bug"} and not criteria:
        missing.append("Acceptance criteria are missing.")
    if item["workItemType"].casefold() == "bug" and not re.search(r"\b(?:actual|expected|repro|steps?)\b", item["description"], flags=re.IGNORECASE):
        missing.append("Bug reproduction details and expected behavior are missing.")
    return missing


def _dependencies(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [value for value in links if value["isDependency"]]


def _summary(item: dict[str, Any]) -> str:
    description = item["description"]
    first = re.split(r"(?<=[.!?])\s+", description)[0] if description else ""
    return first or f"{item['workItemType']} {item['title']} requires additional requirement detail."


def _summary_text(item: dict[str, Any], criteria: list[str], dependencies: list[dict[str, Any]], missing: list[str]) -> str:
    sections = [
        ("Requirement Summary", [_summary(item)]),
        ("Description", [item["description"]]),
        ("Acceptance Criteria", criteria),
        ("Dependencies", [f"Work item {value['workItemId']} ({value['relationship']})" for value in dependencies]),
        ("Missing Information", missing),
        ("Area and Iteration", [f"Area: {item['area'] or 'Not assigned'}", f"Iteration: {item['iteration'] or 'Not assigned'}"]),
    ]
    return "\n\n".join(f"{heading}:\n" + "\n".join(f"- {line}" for line in lines if line) for heading, lines in sections if any(lines))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
