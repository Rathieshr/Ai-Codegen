"""Visual planning projection over persisted HEI and synchronized ADO state."""

from __future__ import annotations

from copy import deepcopy
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
        artifact_updater: Callable[[str, dict[str, Any], str], dict[str, Any]] | None = None,
        artifact_creator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        artifact_regenerator: Callable[[str, str], dict[str, Any]] | None = None,
        artifact_transitioner: Callable[[str, str, str, str, int | None, int | None], dict[str, Any]] | None = None,
        work_item_provider: Callable[[str], list[dict[str, Any]]] | None = None,
        recommendation_provider: Callable[[], list[dict[str, Any]]] | None = None,
        recommendation_approver: Callable[[str, str], dict[str, Any]] | None = None,
        recommendation_rejecter: Callable[[str, str], dict[str, Any]] | None = None,
        estimate_provider: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.artifact_provider = artifact_provider
        self.artifact_approver = artifact_approver
        self.artifact_rejecter = artifact_rejecter
        self.artifact_updater = artifact_updater
        self.artifact_creator = artifact_creator
        self.artifact_regenerator = artifact_regenerator
        self.artifact_transitioner = artifact_transitioner
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

    def hierarchy(self, planning_id: str, project_id: str = "") -> dict[str, Any]:
        """Return one editable hierarchy rooted at the requested planning artifact."""
        records = self._with_hierarchy(self._records(project_id, self.recommendation_provider(), self.estimate_provider(project_id)))
        item = next((entry for entry in records if entry["id"] == planning_id), None)
        if not item:
            raise LookupError(f"Planning item {planning_id} was not found.")
        scope = _planning_scope(item, records)
        return {
            "schemaVersion": "hei-planning-hierarchy-v1",
            "planningId": planning_id,
            "root": item,
            "nodes": scope,
            "allowedTypes": list(PLANNING_TYPES),
            "editable": all(node.get("source") == "planning_artifact" for node in scope),
            "generatedAt": _now(),
        }

    def overview(self, planning_id: str, project_id: str = "") -> dict[str, Any]:
        """Return one deterministic executive projection for a Planning Pack."""
        recommendations = self.recommendation_provider()
        estimates = self.estimate_provider(project_id)
        records = self._with_hierarchy(self._records(project_id, recommendations, estimates))
        item = next((entry for entry in records if entry["id"] == planning_id), None)
        if not item:
            raise LookupError(f"Planning item {planning_id} was not found.")

        scoped = _planning_scope(item, records)
        details = _dict(item.get("details"))
        requirement = _dict(details.get("requirementSummary"))
        analysis = _dict(details.get("requirementAnalysis"))
        hierarchy = _dict(details.get("recommendedHierarchy"))
        estimate = _latest_estimate(estimates, item)
        effective = _dict(estimate.get("effectiveEstimate"))
        report = _dict(effective.get("report"))
        repository = _dict(requirement.get("repository"))
        project_context = _dict(details.get("projectContext"))
        capsule = _dict(details.get("contextCapsule"))
        readiness = _dict(requirement.get("planningReadiness")) or _dict(analysis.get("planningReadiness"))
        dependencies = _unique_strings(requirement.get("dependencies")) or _scope_values(scoped, "dependencies")
        open_questions = _unique_strings(requirement.get("openQuestions"))
        features = _count_scope(scoped, "Feature", hierarchy.get("features"))
        stories = _count_scope(scoped, "Story", hierarchy.get("stories"))
        tasks = _count_scope(scoped, "Task", hierarchy.get("tasks"))
        confidence = _percent(requirement.get("confidence"), fallback=int(item.get("confidence") or effective.get("confidence") or 0))
        quality = _number(requirement.get("qualityScore"), analysis.get("qualityScore"))
        repository_reuse = int(round(float(report.get("repositoryReuse") or effective.get("repositoryReuse") or 0)))
        planning_readiness = _text(readiness.get("status")) or _text(item.get("readiness"))

        return {
            "schemaVersion": "hei-planning-overview-v1",
            "planningId": planning_id,
            "requirement": {
                "name": _text(requirement.get("title")) or _text(item.get("title")),
                "status": _text(item.get("status")),
                "repository": _text(repository.get("name")) or _text(project_context.get("repositoryId")) or "Repository Pending",
                "repositoryId": _text(repository.get("repositoryId")) or _text(project_context.get("repositoryId")),
                "branch": _text(repository.get("branch")) or _text(project_context.get("branch")),
                "confidence": confidence,
                "quality": quality,
                "planningReadiness": planning_readiness,
            },
            "metrics": {
                "engineeringDays": float(report.get("engineeringDays") or effective.get("engineeringDays") or 0),
                "sprintCount": float(report.get("estimatedSprintCount") or effective.get("estimatedSprintCount") or 0),
                "features": features,
                "stories": stories,
                "tasks": tasks,
                "dependencies": len(dependencies),
                "openQuestions": len(open_questions),
                "repositoryReuse": repository_reuse,
            },
            "cards": {
                "planningMetrics": {"features": features, "stories": stories, "tasks": tasks, "dependencies": len(dependencies)},
                "repositorySummary": {
                    "name": _text(repository.get("name")) or "Repository Pending",
                    "branch": _text(repository.get("branch")) or _text(project_context.get("branch")),
                    "mode": _text(capsule.get("status")) or "Pending",
                    "reuse": repository_reuse,
                },
                "engineeringEstimate": {
                    "days": float(report.get("engineeringDays") or effective.get("engineeringDays") or 0),
                    "sprints": float(report.get("estimatedSprintCount") or effective.get("estimatedSprintCount") or 0),
                    "storyPoints": int(report.get("storyPoints") or effective.get("storyPoints") or 0),
                    "risk": _text(report.get("risk") or effective.get("risk")) or "Not assessed",
                },
                "requirementQuality": {"score": quality, "openQuestions": open_questions, "acceptanceCriteria": len(_list(requirement.get("acceptanceCriteria")))},
                "aiConfidence": {"score": confidence, "status": _confidence_label(confidence), "warnings": _unique_strings(capsule.get("warnings"))},
                "recentChanges": _recent_changes(planning_id, self.artifact_provider()),
            },
            "charts": {
                "storyDistribution": _child_distribution(scoped, "Feature", "Story"),
                "taskDistribution": _child_distribution(scoped, "Story", "Task"),
                "estimateBreakdown": _estimate_breakdown(effective),
            },
            "engineeringEstimate": estimate or None,
            "dependencies": dependencies,
            "openQuestions": open_questions,
            "planningReadiness": {
                "status": planning_readiness,
                "score": int(_number(readiness.get("score"), quality)),
                "blockers": _unique_strings(readiness.get("blockers")),
                "warnings": _unique_strings(readiness.get("warnings")) + _unique_strings(capsule.get("warnings")),
            },
            "updatedAt": _text(item.get("updatedAt")),
            "version": int(item.get("version") or 1),
            "generatedAt": _now(),
        }

    def recommendations(self, project_id: str = "", status: str = "") -> dict[str, Any]:
        values = self._recommendation_projection(self.recommendation_provider())
        if project_id:
            values = [item for item in values if not item.get("projectId") or item.get("projectId") == project_id]
        if status:
            values = [item for item in values if _text(item.get("status")).casefold() == status.casefold()]
        return {"recommendations": values[:250], "count": len(values), "generatedAt": _now()}

    def approve(self, planning_id: str, actor: str = "", comments: str = "", expected_version: int | None = None) -> dict[str, Any]:
        recommendation = self._find_recommendation(planning_id)
        if recommendation:
            if not self.recommendation_approver:
                raise ValueError("Recommendation approval is not available.")
            return self.recommendation_approver(planning_id, actor)
        if self.artifact_transitioner:
            return self.artifact_transitioner(planning_id, "approve", actor, comments, expected_version, None)
        return self.artifact_approver(planning_id, actor)

    def reject(self, planning_id: str, actor: str = "", comments: str = "", expected_version: int | None = None) -> dict[str, Any]:
        recommendation = self._find_recommendation(planning_id)
        if recommendation:
            if not self.recommendation_rejecter:
                raise ValueError("Recommendation rejection is not available.")
            return self.recommendation_rejecter(planning_id, actor)
        if self.artifact_transitioner:
            return self.artifact_transitioner(planning_id, "reject", actor, comments, expected_version, None)
        return self.artifact_rejecter(planning_id)

    def request_changes(self, planning_id: str, actor: str = "", comments: str = "", expected_version: int | None = None) -> dict[str, Any]:
        return self._transition(planning_id, "request_changes", actor, comments, expected_version)

    def publish(self, planning_id: str, actor: str = "", comments: str = "", expected_version: int | None = None) -> dict[str, Any]:
        return self._transition(planning_id, "publish", actor, comments, expected_version)

    def rollback(self, planning_id: str, target_version: int, actor: str = "", comments: str = "", expected_version: int | None = None) -> dict[str, Any]:
        return self._transition(planning_id, "rollback", actor, comments, expected_version, target_version)

    def history(self, planning_id: str) -> dict[str, Any]:
        artifact = self._find_artifact(planning_id)
        if not artifact:
            raise LookupError(f"Planning item {planning_id} was not found.")
        values = []
        for entry in _list(artifact.get("history")):
            if not isinstance(entry, dict):
                continue
            values.append(_history_entry(entry, current=False))
        values.append(_history_entry(artifact, current=True))
        values.sort(key=lambda item: (int(item.get("version") or 0), _text(item.get("timestamp"))))
        return {
            "schemaVersion": "hei-planning-approval-history-v1",
            "planningId": planning_id,
            "currentState": _status_label(_text(artifact.get("state")) or "draft"),
            "currentVersion": int(artifact.get("version") or 1),
            "history": values,
            "count": len(values),
            "generatedAt": _now(),
        }

    def _transition(
        self, planning_id: str, action: str, actor: str, comments: str,
        expected_version: int | None, target_version: int | None = None,
    ) -> dict[str, Any]:
        if self._find_recommendation(planning_id):
            raise ValueError(f"Recommendations do not support {action.replace('_', ' ')}.")
        if not self.artifact_transitioner:
            raise ValueError("Enterprise planning lifecycle transitions are not available.")
        return self.artifact_transitioner(planning_id, action, actor, comments, expected_version, target_version)

    def _find_artifact(self, planning_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in _list(_dict(self.artifact_provider()).get("artifacts"))
             if isinstance(item, dict) and _text(item.get("artifact_id")) == planning_id),
            None,
        )

    def update(self, planning_id: str, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        if self._find_recommendation(planning_id):
            raise ValueError("Recommendations are edited through their recommendation workflow.")
        if not self.artifact_updater:
            raise ValueError("Planning draft updates are not available.")
        current = self.get(planning_id)
        if current.get("source") != "planning_artifact":
            raise ValueError("Azure DevOps work items are edited through approved Azure DevOps automation.")
        self.artifact_updater(planning_id, request, actor)
        return self.get(planning_id)

    def save(self, planning_id: str, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        return self.update(planning_id, {**request, "status": request.get("status") or "Draft"}, actor)

    def update_node(self, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        node_id = _text(request.get("nodeId") or request.get("id"))
        if not node_id:
            raise ValueError("nodeId is required.")
        action = _text(request.get("action") or "edit").casefold()
        if action == "duplicate":
            return self._duplicate_node(node_id, request, actor)
        if action == "split":
            return self._split_node(node_id, request, actor)
        if action == "merge":
            return self._merge_nodes(request, actor)
        if action not in {"edit", "move", "reorder"}:
            raise ValueError(f"Unsupported hierarchy action: {action}.")
        current, records = self._editable_node(node_id)
        changes: dict[str, Any] = {
            "expectedVersion": request.get("expectedVersion", current.get("version")),
            "details": {},
        }
        if action == "edit":
            for key in ("title", "description", "status"):
                if key in request:
                    changes[key] = request[key]
            for key in ("storyPoints", "dependencies"):
                if key in request:
                    changes["details"][key] = request[key]
        else:
            parent_id = _text(request.get("parentId"))
            self._validate_parent(current, parent_id, records)
            return self._move_node(current, records, parent_id, max(0, int(request.get("order") or 0)), actor)
        self.artifact_updater(node_id, changes, actor)
        return self.get(node_id)

    def regenerate_node(self, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        node_id = _text(request.get("nodeId") or request.get("id"))
        if not node_id:
            raise ValueError("nodeId is required.")
        self._editable_node(node_id)
        if not self.artifact_regenerator:
            raise ValueError("Planning Intelligence regeneration is not available.")
        self.artifact_regenerator(node_id, actor)
        return self.get(node_id)

    def delete_node(self, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        del actor
        node_id = _text(request.get("nodeId") or request.get("id"))
        if not node_id:
            raise ValueError("nodeId is required.")
        current, records = self._editable_node(node_id)
        descendants = _descendants(node_id, records)
        if descendants and not bool(request.get("cascade")):
            raise ValueError("This node has children. Confirm cascade deletion to archive the subtree.")
        archived = []
        for item in reversed([current] + descendants):
            self.artifact_rejecter(item["id"])
            archived.append(item["id"])
        return {"deleted": True, "archivedNodeIds": archived, "count": len(archived)}

    def _editable_node(self, node_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        records = self._with_hierarchy(self._records("", self.recommendation_provider(), self.estimate_provider("")))
        current = next((item for item in records if item["id"] == node_id), None)
        if not current:
            raise LookupError(f"Planning item {node_id} was not found.")
        if current.get("source") != "planning_artifact":
            raise ValueError("Azure DevOps work items are changed through approved Azure DevOps automation.")
        if not self.artifact_updater:
            raise ValueError("Planning hierarchy updates are not available.")
        if current.get("status") not in {"Draft", "Review"}:
            raise ValueError("Only Draft or Review planning nodes can be changed.")
        return current, records

    def _validate_parent(self, current: dict[str, Any], parent_id: str, records: list[dict[str, Any]]) -> None:
        if current["type"] == "Requirement":
            if parent_id:
                raise ValueError("Requirement is the hierarchy root and cannot have a parent.")
            return
        parent = next((item for item in records if item["id"] == parent_id or item.get("sourceItemId") == parent_id), None)
        if not parent:
            raise ValueError("The selected parent was not found.")
        expected = PLANNING_TYPES[PLANNING_TYPES.index(current["type"]) - 1]
        if parent.get("type") != expected:
            raise ValueError(f"{current['type']} must belong to a {expected}.")
        if parent["id"] == current["id"] or parent["id"] in {item["id"] for item in _descendants(current["id"], records)}:
            raise ValueError("Hierarchy move would create a cycle.")

    def _duplicate_node(self, node_id: str, request: dict[str, Any], actor: str) -> dict[str, Any]:
        current, _records = self._editable_node(node_id)
        if not self.artifact_creator:
            raise ValueError("Planning node duplication is not available.")
        payload = deepcopy(_dict(current.get("details")))
        payload["parentId"] = _text(request.get("parentId")) or current.get("parentId")
        payload["order"] = int(request.get("order") or payload.get("order") or 0) + 1
        payload["duplicatedFrom"] = current["id"]
        payload["duplicateTitle"] = _text(request.get("title")) or f"{current['title']} Copy"
        created = self.artifact_creator({
            "artifact_type": current.get("artifactType") or current["type"], "state": "draft",
            "title": _text(request.get("title")) or f"{current['title']} Copy", "payload": payload,
            "source_item": {"id": current.get("sourceItemId"), "type": current["type"], "title": current["title"]},
            "created_by": actor or "HEI User",
        })
        return self.get(_text(created.get("artifact_id")))

    def _move_node(self, current: dict[str, Any], records: list[dict[str, Any]], parent_id: str, order: int, actor: str) -> dict[str, Any]:
        siblings = [item for item in records if item["id"] != current["id"] and _text(item.get("parentId")) == parent_id]
        siblings.sort(key=lambda item: (int(_dict(item.get("details")).get("order") or 0), item["title"].casefold()))
        position = min(order, len(siblings))
        ordered = siblings[:position] + [current] + siblings[position:]
        impacted = [item for index, item in enumerate(ordered) if int(_dict(item.get("details")).get("order") or 0) != index or item["id"] == current["id"]]
        immutable = [item["title"] for item in impacted if item.get("source") != "planning_artifact" or item.get("status") not in {"Draft", "Review"}]
        if immutable:
            raise ValueError(f"Reordering would modify approved or external siblings: {', '.join(immutable[:3])}.")
        for index, item in enumerate(ordered):
            if item not in impacted:
                continue
            self.artifact_updater(item["id"], {
                "expectedVersion": item.get("version"),
                "details": {"parentId": parent_id, "order": index},
            }, actor)
        return self.get(current["id"])

    def _split_node(self, node_id: str, request: dict[str, Any], actor: str) -> dict[str, Any]:
        current, records = self._editable_node(node_id)
        if _descendants(current["id"], records):
            raise ValueError("Split is available only for leaf nodes. Move or remove child nodes first.")
        titles = [_text(value) for value in _list(request.get("titles")) if _text(value)]
        if len(titles) < 2:
            raise ValueError("Split requires at least two titles.")
        created = [self._duplicate_node(node_id, {**request, "title": title, "order": index}, actor) for index, title in enumerate(titles)]
        if bool(request.get("archiveOriginal", True)):
            self.delete_node({"nodeId": node_id, "cascade": False}, actor)
        return {"action": "split", "nodes": created, "count": len(created)}

    def _merge_nodes(self, request: dict[str, Any], actor: str) -> dict[str, Any]:
        node_ids = [_text(value) for value in _list(request.get("nodeIds")) if _text(value)]
        if len(node_ids) < 2:
            raise ValueError("Merge requires at least two nodes.")
        nodes = [self._editable_node(node_id)[0] for node_id in node_ids]
        if len({(node["type"], node.get("parentId")) for node in nodes}) != 1:
            raise ValueError("Only same-type sibling nodes can be merged.")
        records = self._with_hierarchy(self._records("", self.recommendation_provider(), self.estimate_provider("")))
        if any(_descendants(node["id"], records) for node in nodes):
            raise ValueError("Merge is available only for leaf nodes. Move or remove child nodes first.")
        merged = self._duplicate_node(nodes[0]["id"], {
            "title": _text(request.get("title")) or " / ".join(node["title"] for node in nodes),
            "parentId": nodes[0].get("parentId"), "order": min(int(_dict(node.get("details")).get("order") or 0) for node in nodes),
        }, actor)
        self.artifact_updater(merged["id"], {
            "expectedVersion": merged["version"],
            "description": "\n\n".join(node["description"] for node in nodes if node.get("description")),
            "details": {"mergedFrom": node_ids, "dependencies": _unique_strings([value for node in nodes for value in node.get("dependencies", [])])},
        }, actor)
        for node in nodes:
            self.artifact_rejecter(node["id"])
        return {"action": "merge", "node": self.get(merged["id"]), "archivedNodeIds": node_ids}

    def _records(self, project_id: str, recommendations: list[dict[str, Any]], estimates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recommendation_counts: dict[str, int] = {}
        for item in recommendations:
            key = _text(item.get("workItemId"))
            recommendation_counts[key] = recommendation_counts.get(key, 0) + 1
        estimate_by_item: dict[str, dict[str, Any]] = {}
        for estimate in estimates:
            if not isinstance(estimate, dict):
                continue
            for key in (estimate.get("workItemId"), estimate.get("artifactId"), estimate.get("artifact_id")):
                if _text(key):
                    current = estimate_by_item.get(_text(key))
                    if current is None or (int(estimate.get("version") or 0), _text(estimate.get("updatedAt"))) >= (int(current.get("version") or 0), _text(current.get("updatedAt"))):
                        estimate_by_item[_text(key)] = estimate
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
            project_id=_text(item.get("projectId") or item.get("project_id")),
        )

    def _artifact(self, item: dict[str, Any], recommendation_counts: dict[str, int], estimates: dict[str, dict[str, Any]]) -> dict[str, Any]:
        artifact_id = _text(item.get("artifact_id"))
        payload = _dict(item.get("payload"))
        source = _dict(item.get("source_item"))
        source_id = _text(source.get("id"))
        kind = _normalize_type(item.get("artifact_type"))
        estimate = estimates.get(artifact_id) or estimates.get(source_id, {})
        state = _text(item.get("state")) or "draft"
        approval = "Approved" if state.casefold() in {"approved", "locked", "published"} else "Rejected" if state.casefold() in {"rejected", "archived"} else "Pending"
        parent_id = _lineage_parent(payload) or source_id
        project_context = _dict(payload.get("projectContext"))
        requirement_summary = _dict(payload.get("requirementSummary"))
        effective_estimate = _dict(estimate.get("effectiveEstimate"))
        return _record(
            id=artifact_id, kind=kind, title=_text(item.get("title")) or _text(source.get("title")) or kind,
            description=_description(payload), parent_id=parent_id, status=_status_label(state), approval=approval,
            story_points=int(estimate.get("storyPoints") or effective_estimate.get("storyPoints") or payload.get("storyPoints") or payload.get("story_points") or 0),
            dependencies=_dependencies(payload) or _dependencies(requirement_summary) or _dependencies(estimate),
            risks=_risks(payload, requirement_summary, estimate), confidence=_confidence(payload) or _confidence(requirement_summary),
            recommendation_count=recommendation_counts.get(source_id, 0), source="planning_artifact", source_item_id=source_id,
            updated_at=_text(item.get("updated_on") or item.get("approved_on") or item.get("created_on")), can_approve=state.casefold() in {"draft", "review"},
            version=int(item.get("version") or 1), artifact_type=_text(item.get("artifact_type")), payload=payload,
            project_id=_text(project_context.get("projectId") or requirement_summary.get("projectId")),
            approver=_text(item.get("approved_by")), approval_comments=_text(item.get("last_comments")),
            approved_at=_text(item.get("approved_on")), lifecycle_state=state,
            can_request_changes=state.casefold() in {"review", "approved", "rejected"},
            can_publish=state.casefold() == "approved", can_rollback=any("payload" in entry for entry in _list(item.get("history")) if isinstance(entry, dict)),
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
            can_approve=status.casefold() in {"draft", "needsreview"}, project_id=_text(item.get("projectId")),
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
        records.sort(key=lambda item: (
            item.get("depth", 0), rank.get(item.get("type"), 99),
            int(_dict(item.get("details")).get("order") or 0), item.get("title", "").casefold(),
        ))
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
            artifact_type: str = "", payload: dict[str, Any] | None = None, project_id: str = "",
            approver: str = "", approval_comments: str = "", approved_at: str = "", lifecycle_state: str = "",
            can_request_changes: bool = False, can_publish: bool = False, can_rollback: bool = False) -> dict[str, Any]:
    readiness = "Ready" if approval == "Approved" and not risks else "Needs Review" if risks or confidence < 70 else "In Progress"
    risk_level = "High" if len(risks) >= 3 else "Medium" if risks else "Low"
    return {
        "id": id, "type": kind, "title": title, "description": description, "parentId": parent_id,
        "status": status, "approvalStatus": approval, "storyPoints": story_points, "dependencies": dependencies,
        "readiness": readiness, "risks": risks, "riskLevel": risk_level, "confidence": confidence,
        "recommendationCount": recommendation_count, "source": source, "sourceItemId": source_item_id,
        "updatedAt": updated_at, "version": version, "artifactType": artifact_type, "projectId": project_id,
        "canApprove": can_approve, "canReject": can_approve, "canGenerateExecutionPackage": kind in {"Story", "Task"} and approval == "Approved",
        "canRequestChanges": can_request_changes, "canPublish": can_publish, "canRollback": can_rollback,
        "approver": approver, "approvalComments": approval_comments, "approvedAt": approved_at,
        "lifecycleState": lifecycle_state or status.casefold(),
        "azureDevOpsSyncReady": source == "planning_artifact" and status == "Published",
        "details": payload or {},
    }


def _normalize_type(value: Any) -> str:
    text = _text(value).casefold().replace("_", " ")
    if "planning pack" in text or "planningpack" in text:
        return "Requirement"
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
    requirement = _dict(payload.get("requirementSummary"))
    for key in ("summary", "planningRequirement"):
        if _text(requirement.get(key)):
            return _text(requirement.get(key))
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
    return {"locked": "Approved", "approved": "Approved", "published": "Published", "rejected": "Rejected", "archived": "Archived", "draft": "Draft", "review": "Review"}.get(state.casefold(), state.title())


def _history_entry(value: dict[str, Any], *, current: bool) -> dict[str, Any]:
    state = _text(value.get("state")) or "draft"
    return {
        "version": int(value.get("version") or 1),
        "status": _status_label(state),
        "action": _text(value.get("last_action") if current else value.get("action")) or ("current" if current else "updated"),
        "actor": _text(value.get("last_changed_by") or value.get("approved_by") if current else value.get("changed_by")) or "HEI",
        "comments": _text(value.get("last_comments") if current else value.get("comments")),
        "timestamp": _text(value.get("updated_on") or value.get("approved_on") or value.get("created_on") if current else value.get("changed_on")),
        "title": _text(value.get("title")),
        "isCurrent": current,
        "canRollback": not current and "payload" in value and "title" in value,
    }


def _planning_scope(root: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        by_parent.setdefault(_text(item.get("parentId")), []).append(item)
    result = [root]
    visited = {root["id"]}
    queue = [value for value in (root["id"], _text(root.get("sourceItemId"))) if value]
    while queue:
        parent = queue.pop(0)
        for child in by_parent.get(parent, []):
            if child["id"] in visited:
                continue
            visited.add(child["id"])
            result.append(child)
            queue.extend(value for value in (child["id"], _text(child.get("sourceItemId"))) if value)
    return result


def _descendants(parent_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        by_parent.setdefault(_text(item.get("parentId")), []).append(item)
    result: list[dict[str, Any]] = []
    visited = {parent_id}
    queue = [parent_id]
    while queue:
        current = queue.pop(0)
        for child in by_parent.get(current, []):
            if child["id"] in visited:
                continue
            visited.add(child["id"])
            result.append(child)
            queue.append(child["id"])
    return result


def _latest_estimate(estimates: list[dict[str, Any]], item: dict[str, Any]) -> dict[str, Any]:
    identifiers = {_text(item.get("id")), _text(item.get("sourceItemId"))}
    matches = [
        estimate for estimate in estimates if isinstance(estimate, dict)
        and _text(estimate.get("artifactId") or estimate.get("artifact_id") or estimate.get("workItemId")) in identifiers
    ]
    return max(matches, key=lambda value: (int(value.get("version") or 0), _text(value.get("updatedAt"))), default={})


def _count_scope(scope: list[dict[str, Any]], kind: str, embedded: Any) -> int:
    actual = sum(1 for item in scope if item.get("type") == kind)
    return actual or len(_list(embedded))


def _scope_values(scope: list[dict[str, Any]], key: str) -> list[str]:
    return _unique_strings([value for item in scope for value in _list(item.get(key))])


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in _list(values):
        if isinstance(value, dict):
            text = _text(value.get("question") or value.get("text") or value.get("name") or value.get("title") or value.get("reason"))
        else:
            text = _text(value)
        if text and text not in result:
            result.append(text)
    return result[:50]


def _number(*values: Any) -> int:
    for value in values:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            continue
    return 0


def _percent(value: Any, *, fallback: int = 0) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return max(0, min(100, fallback))
    return max(0, min(100, round(number * 100 if 0 < number <= 1 else number)))


def _confidence_label(value: int) -> str:
    return "High" if value >= 85 else "Moderate" if value >= 70 else "Needs Review"


def _child_distribution(scope: list[dict[str, Any]], parent_type: str, child_type: str) -> list[dict[str, Any]]:
    parents = [item for item in scope if item.get("type") == parent_type]
    values = []
    for parent in parents:
        identifiers = {parent.get("id"), parent.get("sourceItemId")}
        count = sum(1 for item in scope if item.get("type") == child_type and item.get("parentId") in identifiers)
        values.append({"label": _text(parent.get("title")), "value": count})
    return sorted(values, key=lambda value: (-value["value"], value["label"].casefold()))[:12]


def _estimate_breakdown(effective: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for task in _list(effective.get("taskEstimates")):
        if not isinstance(task, dict):
            continue
        hours = float(task.get("estimatedDurationHours") or 0)
        values.append({
            "label": _text(task.get("taskName") or task.get("title")) or "Engineering task",
            "value": round(hours, 1),
            "unit": "hours",
        })
    return sorted(values, key=lambda value: (-value["value"], value["label"].casefold()))[:10]


def _recent_changes(planning_id: str, artifact_result: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = _list(_dict(artifact_result).get("artifacts"))
    artifact = next((item for item in artifacts if isinstance(item, dict) and _text(item.get("artifact_id")) == planning_id), {})
    changes = []
    for entry in _list(_dict(artifact).get("history")):
        if not isinstance(entry, dict):
            continue
        changes.append({
            "status": _status_label(_text(entry.get("state")) or "draft"),
            "version": int(entry.get("version") or 1),
            "actor": _text(entry.get("changed_by")) or "HEI",
            "changedAt": _text(entry.get("changed_on")),
        })
    if artifact:
        changes.append({
            "status": _status_label(_text(artifact.get("state")) or "draft"),
            "version": int(artifact.get("version") or 1),
            "actor": _text(artifact.get("approved_by") or artifact.get("created_by")) or "HEI",
            "changedAt": _text(artifact.get("updated_on") or artifact.get("approved_on") or artifact.get("created_on")),
        })
    return sorted(changes, key=lambda value: value["changedAt"], reverse=True)[:6]
