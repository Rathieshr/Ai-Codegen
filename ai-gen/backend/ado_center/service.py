"""Read-only Azure DevOps Intelligence projection for the Command Center."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict_values(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(item) for item in value.values() if isinstance(item, dict)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


class AzureDevOpsCenterService:
    """Combines synchronized ADO records with HEI intelligence without writing to ADO."""

    def __init__(
        self,
        *,
        sync_service: Any,
        connection_provider: Callable[[], list[dict[str, Any]]],
        sprint_service: Any | None = None,
        recommendation_provider: Callable[[], Any] = lambda: [],
        pr_report_provider: Callable[[], Any] = lambda: {},
        action_pack_provider: Callable[[], Any] = lambda: {},
    ) -> None:
        self.sync_service = sync_service
        self.connection_provider = connection_provider
        self.sprint_service = sprint_service
        self.recommendation_provider = recommendation_provider
        self.pr_report_provider = pr_report_provider
        self.action_pack_provider = action_pack_provider

    def dashboard(self, project_id: str = "") -> dict[str, Any]:
        context = self._context(project_id)
        sprint = self._sprint(context)
        work_items = self._work_items(context, limit=250)
        pull_requests = self._pull_requests(context, limit=250)
        recommendations = self._recommendations(context["projectId"])
        builds = self._builds(context)
        releases = self._releases(context)
        blocked = [item for item in work_items["items"] if item["blocked"]]
        risks = sprint.get("deliveryRisks") or []
        action_packs = self._action_packs(context["projectId"])
        return {
            "schemaVersion": "hei-ado-center-v1",
            "connection": context["connection"], "connected": context["connected"], "projectId": context["projectId"],
            "sync": context["sync"], "sprint": sprint,
            "summary": {
                "workItems": work_items["pagination"]["total"], "pullRequests": pull_requests["pagination"]["total"],
                "openPullRequests": sum(item["open"] for item in pull_requests["items"]),
                "recommendations": len(recommendations), "pendingRecommendations": sum(item["actionable"] for item in recommendations),
                "builds": len(builds), "failedBuilds": sum(item["failed"] for item in builds),
                "releases": len(releases), "blockedWork": len(blocked), "deliveryRisks": len(risks),
                "pendingActions": sum(item["actionable"] for item in action_packs),
            },
            "burndown": sprint.get("burndownSeries") or [],
            "velocity": (sprint.get("metrics") or {}).get("velocity") or _empty_velocity(),
            "blockedWork": blocked[:20], "deliveryRisk": risks[:20],
            "builds": builds[:20], "releases": releases[:20], "recommendations": recommendations[:20],
            "actionPacks": action_packs[:20], "warnings": context["warnings"], "generatedAt": _now(),
        }

    def sprint(self, project_id: str = "", team_id: str = "") -> dict[str, Any]:
        context = self._context(project_id)
        if not context["connected"]:
            return _empty_sprint(context["projectId"], "Disconnected", "Connect and synchronize Azure DevOps to view sprint intelligence.")
        if not context["projectId"]:
            return _empty_sprint("", "ProjectRequired", "Select an Azure DevOps project to view sprint intelligence.")
        try:
            report = self.sprint_service.current(context["projectId"], team_id) if self.sprint_service else None
            return report if isinstance(report, dict) else _empty_sprint(context["projectId"], "Unavailable", "Sprint Intelligence is unavailable.")
        except (LookupError, ValueError):
            return _empty_sprint(context["projectId"], "NoSprint", "No current sprint is synchronized for this project.")

    def work_items(self, project_id: str = "", *, search: str = "", state: str = "", item_type: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        return self._work_items(self._context(project_id), search=search, state=state, item_type=item_type, offset=offset, limit=limit)

    def pull_requests(self, project_id: str = "", *, search: str = "", status: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        return self._pull_requests(self._context(project_id), search=search, status=status, offset=offset, limit=limit)

    def _context(self, project_id: str) -> dict[str, Any]:
        connections = self.connection_provider() or []
        connection = (
            next((item for item in connections if _text(item.get("projectId")) == project_id), {})
            if project_id
            else (connections[0] if len(connections) == 1 else {})
        )
        resolved = project_id or _text(connection.get("projectId"))
        connected = bool(connection and _text(connection.get("status")).casefold() in {"connected", "healthy", "validated"})
        warnings: list[dict[str, str]] = []
        if not connections:
            warnings.append({"code": "ado_disconnected", "message": "Azure DevOps is not connected."})
        elif not resolved:
            warnings.append({"code": "project_required", "message": "Select an Azure DevOps project."})
        cache = self.sync_service.cache.snapshot(resolved) if resolved else {}
        sync = self.sync_service.status(resolved) if resolved else {"projectId": "", "latestSync": None, "collectionCounts": {}, "centralized": True, "sourceOfTruth": "Azure DevOps"}
        if not connected and cache:
            warnings.append({"code": "cached_data", "message": "Showing the last synchronized Azure DevOps data while the connection is unavailable."})
        return {"projectId": resolved, "connection": _public_connection(connection), "connected": connected, "cache": cache, "sync": sync, "warnings": warnings}

    def _sprint(self, context: dict[str, Any]) -> dict[str, Any]:
        return self.sprint(context["projectId"]) if context["projectId"] else _empty_sprint("", "ProjectRequired", "Select an Azure DevOps project to view sprint intelligence.")

    def _work_items(self, context: dict[str, Any], *, search: str = "", state: str = "", item_type: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        recommendations = self._recommendations(context["projectId"])
        counts: dict[str, int] = {}
        for item in recommendations:
            key = item["workItemId"]
            counts[key] = counts.get(key, 0) + 1
        records = []
        for source in _dict_values((context["cache"] or {}).get("workItems")):
            item_id = _text(source.get("workItemId") or source.get("id"))
            tags = source.get("tags") if isinstance(source.get("tags"), list) else [entry.strip() for entry in _text(source.get("tags")).split(";") if entry.strip()]
            links = source.get("links") if isinstance(source.get("links"), list) else []
            blocked = _text(source.get("state")).casefold() == "blocked" or any(_text(tag).casefold() == "blocked" for tag in tags) or any("dependency" in _text(link.get("relation") or link.get("rel")).casefold() for link in links if isinstance(link, dict))
            records.append({
                "workItemId": item_id, "title": _text(source.get("title")) or f"Work Item {item_id}",
                "type": _text(source.get("workItemType") or source.get("type")) or "Work Item", "state": _text(source.get("state")) or "Unknown",
                "assignedTo": _identity(source.get("assignedTo")), "iterationPath": _text(source.get("iterationPath")),
                "storyPoints": source.get("storyPoints"), "effort": source.get("effort"),
                "originalEstimate": source.get("originalEstimate"), "remainingWork": source.get("remainingWork"),
                "completedWork": source.get("completedWork"), "blocked": blocked, "recommendationCount": counts.get(item_id, 0),
                "webUrl": _text(source.get("url") or source.get("webUrl")), "changedAt": _text(source.get("changedAt")),
            })
        query = search.strip().casefold()
        records = [item for item in records if (not query or query in f"{item['title']} {item['workItemId']} {item['type']}".casefold()) and (not state or item["state"].casefold() == state.casefold()) and (not item_type or item["type"].casefold() == item_type.casefold())]
        records.sort(key=lambda item: (item["blocked"] is False, item["changedAt"]), reverse=False)
        return self._page("workItems", records, offset, limit, context)

    def _pull_requests(self, context: dict[str, Any], *, search: str = "", status: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        reports = _dict_values(self.pr_report_provider())
        reports_by_pr = {_text(item.get("pullRequestId")): item for item in reports if item.get("pullRequestId")}
        records = []
        for source in _dict_values((context["cache"] or {}).get("pullRequests")):
            pr_id = _text(source.get("pullRequestId") or source.get("id"))
            report = reports_by_pr.get(pr_id, {})
            raw_status = _text(source.get("status")) or "Unknown"
            records.append({
                "pullRequestId": pr_id, "title": _text(source.get("title")) or f"Pull Request {pr_id}", "status": raw_status,
                "open": raw_status.casefold() in {"active", "open", "notset"}, "createdBy": _identity(source.get("createdBy")),
                "sourceBranch": _text(source.get("sourceBranch")), "targetBranch": _text(source.get("targetBranch")),
                "linkedWorkItemIds": source.get("linkedWorkItemIds") or [], "webUrl": _text(source.get("url") or source.get("webUrl")),
                "intelligenceStatus": _text(report.get("status")) or "NotAnalyzed", "risk": report.get("risk") or {},
                "missingTests": len(report.get("missingTests") or []), "acceptanceCoverage": (report.get("acceptanceCoverage") or {}).get("score"),
            })
        query = search.strip().casefold()
        records = [item for item in records if (not query or query in f"{item['title']} {item['pullRequestId']} {item['sourceBranch']}".casefold()) and (not status or item["status"].casefold() == status.casefold())]
        records.sort(key=lambda item: (not item["open"], item["pullRequestId"]))
        return self._page("pullRequests", records, offset, limit, context)

    def _recommendations(self, project_id: str) -> list[dict[str, Any]]:
        records = []
        for source in _dict_values(self.recommendation_provider()):
            if project_id and source.get("projectId") and _text(source.get("projectId")) != project_id:
                continue
            status = _text(source.get("status")) or "Draft"
            proposed = source.get("proposedValue")
            records.append({
                "recommendationId": _text(source.get("recommendationId")), "workItemId": _text(source.get("workItemId")),
                "type": _text(source.get("recommendationType")) or "Recommendation", "status": status,
                "title": _text(proposed.get("title") if isinstance(proposed, dict) else proposed) or _text(source.get("recommendationType")),
                "confidence": source.get("confidence"), "actionable": status.casefold() in {"draft", "needsreview"},
            })
        return records

    def _builds(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        records = []
        for source in _dict_values((context["cache"] or {}).get("builds")):
            result = _text(source.get("result"))
            records.append({"buildId": _text(source.get("buildId") or source.get("id")), "buildNumber": _text(source.get("buildNumber")), "definitionName": _text(source.get("definitionName")), "status": _text(source.get("status")), "result": result, "failed": result.casefold() in {"failed", "partiallysucceeded", "canceled", "cancelled"}, "webUrl": _text(source.get("url") or source.get("webUrl")), "finishedAt": _text(source.get("finishTime"))})
        return sorted(records, key=lambda item: item["finishedAt"], reverse=True)

    def _releases(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"releaseId": _text(item.get("releaseId") or item.get("id")), "name": _text(item.get("name")), "status": _text(item.get("status")), "webUrl": _text(item.get("url") or item.get("webUrl"))} for item in _dict_values((context["cache"] or {}).get("releases"))]

    def _action_packs(self, project_id: str) -> list[dict[str, Any]]:
        value = self.action_pack_provider()
        sources = value.get("actionPacks") if isinstance(value, dict) else value
        records = []
        for item in _dict_values(sources):
            if project_id and item.get("projectId") and _text(item.get("projectId")) != project_id:
                continue
            status = _text(item.get("approvalStatus") or item.get("status"))
            records.append({"packId": _text(item.get("packId")), "trigger": _text(item.get("trigger")), "status": status, "actionable": status.casefold() in {"pendingapproval", "prepared"}, "expiresAt": _text(item.get("expiresAt"))})
        return records

    @staticmethod
    def _page(key: str, records: list[dict[str, Any]], offset: int, limit: int, context: dict[str, Any]) -> dict[str, Any]:
        safe_offset, safe_limit = max(0, offset), min(250, max(1, limit))
        page = records[safe_offset:safe_offset + safe_limit]
        return {"schemaVersion": "hei-ado-center-v1", "projectId": context["projectId"], "connected": context["connected"], key: page, "items": page, "warnings": context["warnings"], "pagination": {"total": len(records), "offset": safe_offset, "limit": safe_limit, "returned": len(page), "hasMore": safe_offset + len(page) < len(records)}, "generatedAt": _now()}


def _identity(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("displayName") or value.get("name") or value.get("uniqueName"))
    return _text(value)


def _public_connection(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value.get(key) for key in ("connectionId", "organizationUrl", "organizationName", "projectId", "projectName", "status", "permissions", "lastValidatedAt", "validationMessage") if value.get(key) not in (None, "")}


def _empty_velocity() -> dict[str, Any]:
    return {"currentCompletedStoryPoints": 0, "historicalAverageStoryPoints": None, "historicalSprintCount": 0, "status": "Unavailable"}


def _empty_sprint(project_id: str, status: str, message: str) -> dict[str, Any]:
    return {"projectId": project_id, "status": status, "health": status, "message": message, "iteration": {}, "metrics": {"plannedScope": {"itemCount": 0, "storyPoints": 0}, "completedScope": {"itemCount": 0, "storyPoints": 0}, "remainingScope": {"itemCount": 0, "storyPoints": 0}, "velocity": _empty_velocity()}, "burndownSeries": [], "currentBlockers": [], "deliveryRisks": [], "forecast": {"status": "Unavailable", "forecastDate": None, "onTrack": None}, "completionConfidence": {"score": 0, "level": "Low", "reasons": [message]}, "generatedAt": _now()}
