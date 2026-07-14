"""Visual planning projection over persisted HEI and synchronized ADO state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


PLANNING_TYPES = ("Requirement", "Epic", "Feature", "Story", "Task")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class PlanningCenterService:
    """Builds a bounded UI projection without owning planning generation."""

    def __init__(
        self,
        *,
        artifact_provider: Callable[[], dict[str, Any]],
        artifact_approver: Callable[[str, str], dict[str, Any]],
        artifact_rejecter: Callable[[str], dict[str, Any]],
        work_item_provider: Callable[[str], list[dict[str, Any]]] | None = None,
        recommendation_provider: Callable[[], list[dict[str, Any]]] | None = None,
        recommendation_approver: Callable[[str, str], dict[str, Any]] | None = None,
        recommendation_rejecter: Callable[[str, str], dict[str, Any]] | None = None,
        estimate_provider: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.artifact_provider = artifact_provider
        self.artifact_approver = artifact_approver
        self.artifact_rejecter = artifact_rejecter
        self.work_item_provider = work_item_provider or (lambda _project_id: [])
        self.recommendation_provider = recommendation_provider or (lambda: [])
        self.recommendation_approver = recommendation_approver
        self.recommendation_rejecter = recommendation_rejecter
        self.estimate_provider = estimate_provider or (lambda _project_id: [])

    def list(
        self,
        *,
        project_id: str = "",
        search: str = "",
        item_type: str = "",
        status: str = "",
        readiness: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        recommendations = self.recommendation_provider()
        estimates = self.estimate_provider(project_id)
        records = self._records(project_id, recommendations, estimates)
        records = self._with_hierarchy(records)
        summary = self._summary(records, recommendations)
        filtered = self._filter(records, search, item_type, status, readiness)
        safe_offset = max(0, offset)
        safe_limit = min(250, max(1, limit))
        page = filtered[safe_offset:safe_offset + safe_limit]
        return {
            "schemaVersion": "hei-planning-center-v1",
            "summary": summary,
            "items": page,
            "recommendations": self._recommendation_projection(recommendations)[:100],
            "filters": {
                "types": list(PLANNING_TYPES),
                "statuses": sorted({_text(item.get("status")) for item in records if item.get("status")}),
                "readiness": sorted({_text(item.get("readiness")) for item in records if item.get("readiness")}),
            },
            "pagination": {
                "total": len(filtered), "offset": safe_offset, "limit": safe_limit,
                "returned": len(page), "hasMore": safe_offset + len(page) < len(filtered),
            },
            "query": {"search": search, "type": item_type, "status": status, "readiness": readiness},
            "generatedAt": _now(),
        }

    def get(self, planning_id: str, project_id: str = "") -> dict[str, Any]:
        recommendations = self.recommendation_provider()
        records = self._with_hierarchy(self._records(project_id, recommendations, self.estimate_provider(project_id)))
        item = next((entry for entry in records if entry["id"] == planning_id), None)
        if not item:
            raise LookupError(f"Planning item {planning_id} was not found.")
        children = [entry for entry in records if entry.get("parentId") in {planning_id, item.get("sourceItemId")}]
        related = [entry for entry in self._recommendation_projection(recommendations) if entry.get("workItemId") in {planning_id, item.get("sourceItemId")}]
        return {**item, "children": children, "recommendations": related}

    def recommendations(self, project_id: str = "", status: str = "") -> dict[str, Any]:
        values = self._recommendation_projection(self.recommendation_provider())
        if project_id:
            values = [item for item in values if not item.get("projectId") or item.get("projectId") == project_id]
        if status:
            values = [item for item in values if _text(item.get("status")).casefold() == status.casefold()]
        return {"recommendations": values[:250], "count": len(values), "generatedAt": _now()}

    def approve(self, planning_id: str, actor: str = "") -> dict[str, Any]:
        recommendation = self._find_recommendation(planning_id)
        if recommendation:
            if not self.recommendation_approver:
                raise ValueError("Recommendation approval is not available.")
            return self.recommendation_approver(planning_id, actor)
        return self.artifact_approver(planning_id, actor)

    def reject(self, planning_id: str, actor: str = "") -> dict[str, Any]:
        recommendation = self._find_recommendation(planning_id)
        if recommendation:
            if not self.recommendation_rejecter:
                raise ValueError("Recommendation rejection is not available.")
            return self.recommendation_rejecter(planning_id, actor)
        return self.artifact_rejecter(planning_id)

    def _records(self, project_id: str, recommendations: list[dict[str, Any]], estimates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recommendation_counts: dict[str, int] = {}
        for item in recommendations:
            key = _text(item.get("workItemId"))
            recommendation_counts[key] = recommendation_counts.get(key, 0) + 1
        estimate_by_item = {_text(item.get("workItemId")): item for item in estimates}
        values = [self._work_item(item, recommendation_counts, estimate_by_item) for item in self.work_item_provider(project_id)]
        artifacts = _list(self.artifact_provider().get("artifacts"))
        values.extend(self._artifact(item, recommendation_counts, estimate_by_item) for item in artifacts if isinstance(item, dict))
        values.extend(self._recommendation_item(item) for item in recommendations)
        deduped: dict[str, dict[str, Any]] = {}
        for item in values:
            if not item or item.get("type") not in PLANNING_TYPES and item.get("type") != "Recommendation":
                continue
            key = item["id"]
            previous = deduped.get(key)
            if previous is None or _text(item.get("updatedAt")) >= _text(previous.get("updatedAt")):
                deduped[key] = item
        return list(deduped.values())

    def _work_item(self, item: dict[str, Any], recommendation_counts: dict[str, int], estimates: dict[str, dict[str, Any]]) -> dict[str, Any]:
        work_item_id = _text(item.get("workItemId") or item.get("id"))
        kind = _normalize_type(item.get("workItemType") or item.get("type"))
        estimate = estimates.get(work_item_id, {})
        return _record(
            id=work_item_id, kind=kind, title=_text(item.get("title")) or f"{kind} {work_item_id}",
            description=_text(item.get("description")), parent_id=_parent_id(item), status=_text(item.get("state")) or "New",
            approval="Approved" if _text(item.get("state")).casefold() in {"approved", "committed", "done", "closed"} else "Pending",
            story_points=int(estimate.get("storyPoints") or item.get("storyPoints") or 0),
            dependencies=_dependencies(estimate or item), risks=_risks(item, estimate), confidence=_confidence(estimate or item),
            recommendation_count=recommendation_counts.get(work_item_id, 0), source="azure_devops", source_item_id=work_item_id,
            updated_at=_text(item.get("changedAt") or item.get("updatedAt")), can_approve=False,
        )

    def _artifact(self, item: dict[str, Any], recommendation_counts: dict[str, int], estimates: dict[str, dict[str, Any]]) -> dict[str, Any]:
        artifact_id = _text(item.get("artifact_id"))
        payload = _dict(item.get("payload"))
        source = _dict(item.get("source_item"))
        source_id = _text(source.get("id"))
        kind = _normalize_type(item.get("artifact_type"))
        estimate = estimates.get(source_id, {})
        state = _text(item.get("state")) or "draft"
        approval = "Approved" if state.casefold() in {"approved", "locked"} else "Rejected" if state.casefold() == "archived" else "Pending"
        parent_id = _lineage_parent(payload) or source_id
        return _record(
            id=artifact_id, kind=kind, title=_text(item.get("title")) or _text(source.get("title")) or kind,
            description=_description(payload), parent_id=parent_id, status=_status_label(state), approval=approval,
            story_points=int(estimate.get("storyPoints") or payload.get("storyPoints") or payload.get("story_points") or 0),
            dependencies=_dependencies(payload) or _dependencies(estimate), risks=_risks(payload, estimate), confidence=_confidence(payload),
            recommendation_count=recommendation_counts.get(source_id, 0), source="planning_artifact", source_item_id=source_id,
            updated_at=_text(item.get("approved_on") or item.get("created_on")), can_approve=state.casefold() == "draft",
            version=int(item.get("version") or 1), artifact_type=_text(item.get("artifact_type")), payload=payload,
        )

    def _recommendation_item(self, item: dict[str, Any]) -> dict[str, Any]:
        proposed = item.get("proposedValue")
        title = _text(proposed.get("title") if isinstance(proposed, dict) else proposed) or _text(item.get("recommendationType"))
        status = _text(item.get("status")) or "Draft"
        return _record(
            id=_text(item.get("recommendationId")), kind="Recommendation", title=title or "Planning recommendation",
            description=" ".join(_text(value) for value in _list(item.get("reasons"))), parent_id=_text(item.get("workItemId")),
            status=status, approval=status, dependencies=[], risks=[], confidence=_confidence(item), recommendation_count=0,
            source="recommendation", source_item_id=_text(item.get("workItemId")), updated_at=_text(item.get("createdAt")),
            can_approve=status.casefold() in {"draft", "needsreview"},
        )

    def _with_hierarchy(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {item["id"]: item for item in records}
        source_lookup = {item.get("sourceItemId"): item["id"] for item in records if item.get("sourceItemId")}
        for item in records:
            parent = item.get("parentId")
            if parent and parent not in by_id and parent in source_lookup and source_lookup[parent] != item["id"]:
                item["parentId"] = source_lookup[parent]
        child_counts: dict[str, int] = {}
        for item in records:
            if item.get("parentId"):
                child_counts[item["parentId"]] = child_counts.get(item["parentId"], 0) + 1
        for item in records:
            depth = 0
            cursor = item.get("parentId")
            visited = {item["id"]}
            while cursor and cursor in by_id and cursor not in visited and depth < 100:
                visited.add(cursor); depth += 1; cursor = by_id[cursor].get("parentId")
            item["depth"] = depth
            item["childCount"] = child_counts.get(item["id"], 0)
        rank = {name: index for index, name in enumerate((*PLANNING_TYPES, "Recommendation"))}
        records.sort(key=lambda item: (item.get("depth", 0), rank.get(item.get("type"), 99), item.get("title", "").casefold()))
        return records

    def _filter(self, records: list[dict[str, Any]], search: str, item_type: str, status: str, readiness: str) -> list[dict[str, Any]]:
        query = search.strip().casefold()
        return [
            item for item in records
            if (not item_type or item.get("type", "").casefold() == item_type.casefold())
            and (not status or item.get("status", "").casefold() == status.casefold() or item.get("approvalStatus", "").casefold() == status.casefold())
            and (not readiness or item.get("readiness", "").casefold() == readiness.casefold())
            and (not query or query in " ".join([
                _text(item.get("title")), _text(item.get("description")), " ".join(item.get("dependencies") or []),
                " ".join(item.get("risks") or []), _text(item.get("type")),
            ]).casefold())
        ]

    def _summary(self, records: list[dict[str, Any]], recommendations: list[dict[str, Any]]) -> dict[str, Any]:
        counts = {
            "requirements": sum(1 for item in records if item.get("type") == "Requirement"),
            "epics": sum(1 for item in records if item.get("type") == "Epic"),
            "features": sum(1 for item in records if item.get("type") == "Feature"),
            "stories": sum(1 for item in records if item.get("type") == "Story"),
            "tasks": sum(1 for item in records if item.get("type") == "Task"),
        }
        return {
            **counts,
            "recommendations": len(recommendations),
            "approved": sum(1 for item in records if item.get("approvalStatus") == "Approved"),
            "needsReview": sum(1 for item in records if item.get("readiness") == "Needs Review"),
            "highRisk": sum(1 for item in records if item.get("riskLevel") == "High"),
            "averageConfidence": round(sum(float(item.get("confidence") or 0) for item in records) / max(1, len(records))),
            "total": len(records),
        }

    def _recommendation_projection(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted([dict(item) for item in values if isinstance(item, dict)], key=lambda item: _text(item.get("createdAt")), reverse=True)

    def _find_recommendation(self, planning_id: str) -> dict[str, Any] | None:
        return next((item for item in self.recommendation_provider() if _text(item.get("recommendationId")) == planning_id), None)


def _record(*, id: str, kind: str, title: str, description: str, parent_id: str, status: str, approval: str,
            story_points: int, dependencies: list[str], risks: list[str], confidence: int, recommendation_count: int,
            source: str, source_item_id: str, updated_at: str, can_approve: bool, version: int = 1,
            artifact_type: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    readiness = "Ready" if approval == "Approved" and not risks else "Needs Review" if risks or confidence < 70 else "In Progress"
    risk_level = "High" if len(risks) >= 3 else "Medium" if risks else "Low"
    return {
        "id": id, "type": kind, "title": title, "description": description, "parentId": parent_id,
        "status": status, "approvalStatus": approval, "storyPoints": story_points, "dependencies": dependencies,
        "readiness": readiness, "risks": risks, "riskLevel": risk_level, "confidence": confidence,
        "recommendationCount": recommendation_count, "source": source, "sourceItemId": source_item_id,
        "updatedAt": updated_at, "version": version, "artifactType": artifact_type,
        "canApprove": can_approve, "canReject": can_approve, "canGenerateExecutionPackage": kind in {"Story", "Task"} and approval == "Approved",
        "details": payload or {},
    }


def _normalize_type(value: Any) -> str:
    text = _text(value).casefold().replace("_", " ")
    if "recommend" in text:
        return "Recommendation"
    if "requirement" in text:
        return "Requirement"
    if "epic" in text:
        return "Epic"
    if "feature" in text:
        return "Feature"
    if "story" in text or "product backlog" in text or text == "pbi":
        return "Story"
    if "task" in text:
        return "Task"
    return _text(value).title() or "Requirement"


def _parent_id(value: dict[str, Any]) -> str:
    parent = value.get("parent")
    return _text(value.get("parentId") or value.get("parentWorkItemId") or (parent.get("id") if isinstance(parent, dict) else ""))


def _lineage_parent(payload: dict[str, Any]) -> str:
    lineage = _dict(payload.get("lineage"))
    for key in ("parentId", "parent_id", "storyId", "featureId", "epicId"):
        value = payload.get(key) or lineage.get(key)
        if value:
            return _text(value)
    dna = _dict(payload.get("dna"))
    return _text(dna.get("parentDNA") or dna.get("parentId"))


def _description(payload: dict[str, Any]) -> str:
    for key in ("description", "businessGoal", "business_goal", "summary", "userStory", "user_story", "objective"):
        if _text(payload.get(key)):
            return _text(payload.get(key))
    return "Planning details are available when this item is opened."


def _dependencies(value: dict[str, Any]) -> list[str]:
    raw = value.get("dependencies") or value.get("primaryDependencies") or value.get("primary_dependencies") or []
    result = []
    for item in _list(raw):
        text = _text(item.get("name") or item.get("title")) if isinstance(item, dict) else _text(item)
        if text and text not in result:
            result.append(text)
    return result[:12]


def _risks(*values: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        for item in _list(value.get("risks")) + _list(value.get("blockers")):
            text = _text(item.get("reason") or item.get("title") or item.get("name")) if isinstance(item, dict) else _text(item)
            if text and text not in result:
                result.append(text)
    return result[:12]


def _confidence(value: dict[str, Any]) -> int:
    raw = value.get("confidence") or _dict(value.get("readiness")).get("confidence") or 0
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return 0
    return round(number * 100 if 0 < number <= 1 else number)


def _status_label(state: str) -> str:
    return {"locked": "Approved", "approved": "Approved", "archived": "Rejected", "draft": "Draft"}.get(state.casefold(), state.title())
