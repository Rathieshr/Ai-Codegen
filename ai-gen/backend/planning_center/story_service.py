"""Story detail projection and editing orchestration for Planning Workspace."""

from __future__ import annotations

from typing import Any, Callable

from .task_service import task_summary


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    result: list[str] = []
    for item in _list(value):
        text = _text(item.get("text") or item.get("title") or item.get("name")) if isinstance(item, dict) else _text(item)
        if text and text not in result:
            result.append(text)
    return result


class StoryDetailService:
    """Projects one Story and delegates mutations to canonical lifecycle services."""

    def __init__(
        self,
        *,
        planning_service: Any,
        artifact_provider: Callable[[], dict[str, Any]],
        task_regenerator: Callable[[str, str], dict[str, Any]],
        test_generator: Callable[[str, str], dict[str, Any]],
    ) -> None:
        self.planning = planning_service
        self.artifact_provider = artifact_provider
        self.task_regenerator = task_regenerator
        self.test_generator = test_generator

    def get(self, story_id: str, project_id: str = "") -> dict[str, Any]:
        story = self.planning.get(story_id, project_id)
        if story.get("type") != "Story":
            raise ValueError(f"Planning item {story_id} is not a Story.")
        payload = _dict(story.get("details"))
        artifacts = [item for item in _list(self.artifact_provider().get("artifacts")) if isinstance(item, dict)]
        children = [item for item in artifacts if _parent_id(_dict(item.get("payload"))) == story_id and _text(item.get("state")).casefold() != "archived"]
        tasks = [task_summary(item) for item in children if "task" in _text(item.get("artifact_type")).casefold()]
        tests: list[dict[str, Any]] = []
        for item in children:
            if "test" not in _text(item.get("artifact_type")).casefold():
                continue
            item_payload = _dict(item.get("payload"))
            suite = _dict(item_payload.get("test_suite"))
            cases = _list(suite.get("test_cases") or item_payload.get("testCases"))
            if cases:
                tests.extend(_test_summary(case, item) for case in cases if isinstance(case, dict))
            else:
                tests.append(_child_summary(item))
        records = self.planning.list(project_id=project_id, limit=250).get("items", [])
        sibling_stories = [
            {"id": item["id"], "title": item["title"], "status": item["status"], "confidence": item["confidence"]}
            for item in records
            if item.get("type") == "Story" and item.get("id") != story_id and item.get("parentId") == story.get("parentId")
        ]
        explicit_related = set(_strings(payload.get("relatedStoryIds")))
        related = [{**item, "selected": item["id"] in explicit_related} for item in sibling_stories]
        modules = _strings(payload.get("repositoryModules") or payload.get("affected_modules") or payload.get("selectedModules"))
        generated_using = _dict(payload.get("generatedUsing"))
        modules = modules or _strings(generated_using.get("modules"))
        persisted_estimate = _latest_estimate(self.planning.estimate_provider(project_id), story)
        return {
            "schemaVersion": "hei-story-detail-v1",
            "id": story["id"], "title": story["title"], "description": story["description"],
            "status": story["status"], "approvalStatus": story["approvalStatus"], "version": story["version"],
            "editable": story.get("source") == "planning_artifact" and story.get("status") in {"Draft", "Review"},
            "acceptanceCriteria": _strings(payload.get("acceptanceCriteria") or payload.get("acceptance_criteria")),
            "businessRules": _strings(payload.get("businessRules") or payload.get("business_rules")),
            "dependencies": list(story.get("dependencies") or []),
            "estimate": _estimate_summary(payload, story, persisted_estimate),
            "storyPoints": int(story.get("storyPoints") or 0),
            "risks": list(story.get("risks") or []), "risk": story.get("riskLevel") or "Low",
            "repositoryModules": modules,
            "relatedStories": related[:20], "generatedTasks": tasks[:50], "generatedTests": tests[:100],
            "engineeringNotes": _strings(payload.get("engineeringNotes") or payload.get("engineering_notes")),
            "updatedAt": story.get("updatedAt"), "parentId": story.get("parentId"),
        }

    def update(self, story_id: str, request: dict[str, Any], actor: str = "", project_id: str = "") -> dict[str, Any]:
        current = self.get(story_id, project_id)
        if not current["editable"]:
            raise ValueError("Only Draft or Review Stories can be edited.")
        self._validate_child_updates(request.get("generatedTasks"), request.get("generatedTests"))
        details = {}
        for key in ("acceptanceCriteria", "businessRules", "dependencies", "estimate", "storyPoints", "risks", "repositoryModules", "engineeringNotes"):
            if key in request:
                details[key] = request[key]
        if "relatedStoryIds" in request:
            details["relatedStoryIds"] = request["relatedStoryIds"]
        self.planning.update(story_id, {
            "expectedVersion": request.get("expectedVersion", current["version"]),
            "title": request.get("title", current["title"]),
            "description": request.get("description", current["description"]),
            "status": request.get("status", current["status"]),
            "details": details,
        }, actor)
        self._update_tasks(request.get("generatedTasks"), actor)
        self._update_tests(request.get("generatedTests"), actor)
        return self.get(story_id, project_id)

    def _validate_child_updates(self, tasks: Any, tests: Any) -> None:
        artifacts = [item for item in _list(self.artifact_provider().get("artifacts")) if isinstance(item, dict)]
        by_id = {_text(item.get("artifact_id")): item for item in artifacts}
        for value in _list(tasks):
            if not isinstance(value, dict) or not _text(value.get("id")):
                continue
            artifact = by_id.get(_text(value.get("id")))
            if artifact and _text(artifact.get("state")).casefold() not in {"draft", "review"}:
                raise ValueError(f"Task {_text(artifact.get('title'))} is approved and cannot be edited from the Story drawer.")
            if artifact and value.get("version") is not None and int(value["version"]) != int(artifact.get("version") or 1):
                raise ValueError(f"Task {_text(artifact.get('title'))} changed. Reload the Story drawer before saving.")
        grouped_versions: dict[str, int] = {}
        for value in _list(tests):
            if not isinstance(value, dict) or not _text(value.get("artifactId")):
                continue
            artifact_id = _text(value.get("artifactId"))
            artifact = by_id.get(artifact_id)
            if artifact and _text(artifact.get("state")).casefold() not in {"draft", "review"}:
                raise ValueError(f"Test Suite {_text(artifact.get('title'))} is approved and cannot be edited from the Story drawer.")
            expected = int(value.get("artifactVersion") or (artifact or {}).get("version") or 1)
            if artifact and expected != int(artifact.get("version") or 1):
                raise ValueError(f"Test Suite {_text(artifact.get('title'))} changed. Reload the Story drawer before saving.")
            if artifact_id in grouped_versions and grouped_versions[artifact_id] != expected:
                raise ValueError("Generated Tests contain conflicting artifact versions.")
            grouped_versions[artifact_id] = expected

    def regenerate(self, story_id: str, actor: str = "", project_id: str = "") -> dict[str, Any]:
        self.planning.regenerate_node({"nodeId": story_id}, actor)
        return self.get(story_id, project_id)

    def regenerate_tasks(self, story_id: str, actor: str = "", project_id: str = "") -> dict[str, Any]:
        result = self.task_regenerator(story_id, actor)
        return {"story": self.get(story_id, project_id), "generation": result}

    def generate_tests(self, story_id: str, actor: str = "", project_id: str = "") -> dict[str, Any]:
        result = self.test_generator(story_id, actor)
        return {"story": self.get(story_id, project_id), "generation": result}

    def delete(self, story_id: str, actor: str = "") -> dict[str, Any]:
        artifacts = [item for item in _list(self.artifact_provider().get("artifacts")) if isinstance(item, dict)]
        non_planning_children = [
            _text(item.get("artifact_id")) for item in artifacts
            if _parent_id(_dict(item.get("payload"))) == story_id
            and "test" in _text(item.get("artifact_type")).casefold()
            and _text(item.get("state")).casefold() != "archived"
        ]
        result = self.planning.delete_node({"nodeId": story_id, "cascade": True}, actor)
        for artifact_id in non_planning_children:
            self.planning.artifact_rejecter(artifact_id)
        return {
            **result,
            "archivedNodeIds": [*result.get("archivedNodeIds", []), *non_planning_children],
            "count": int(result.get("count") or 0) + len(non_planning_children),
        }

    def _update_tasks(self, values: Any, actor: str) -> None:
        if not isinstance(values, list):
            return
        artifacts = [item for item in _list(self.artifact_provider().get("artifacts")) if isinstance(item, dict)]
        by_id = {_text(item.get("artifact_id")): item for item in artifacts}
        for value in values:
            if not isinstance(value, dict):
                continue
            artifact = by_id.get(_text(value.get("id")))
            if not artifact:
                continue
            if _text(artifact.get("state")).casefold() not in {"draft", "review"}:
                raise ValueError(f"Task {_text(artifact.get('title'))} is approved and cannot be edited from the Story drawer.")
            self.planning.artifact_updater(_text(artifact.get("artifact_id")), {
                "expectedVersion": value.get("version") or artifact.get("version"),
                "title": value.get("title") or artifact.get("title"),
                "description": value.get("description") if "description" in value else _dict(artifact.get("payload")).get("description"),
                "details": {
                    key: value[key] for key in ("category", "estimate", "owner", "priority", "taskStatus", "dependencies")
                    if key in value
                },
            }, actor)

    def _update_tests(self, values: Any, actor: str) -> None:
        if not isinstance(values, list):
            return
        artifacts = [item for item in _list(self.artifact_provider().get("artifacts")) if isinstance(item, dict)]
        by_id = {_text(item.get("artifact_id")): item for item in artifacts}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for value in values:
            if isinstance(value, dict) and _text(value.get("artifactId")):
                grouped.setdefault(_text(value.get("artifactId")), []).append(value)
        for artifact_id, cases in grouped.items():
            artifact = by_id.get(artifact_id)
            if not artifact:
                continue
            if _text(artifact.get("state")).casefold() not in {"draft", "review"}:
                raise ValueError(f"Test Suite {_text(artifact.get('title'))} is approved and cannot be edited from the Story drawer.")
            payload = _dict(artifact.get("payload"))
            suite = _dict(payload.get("test_suite"))
            test_cases = [
                {key: value for key, value in case.items() if key not in {"artifactId", "artifactVersion", "editable", "status"}}
                for case in cases
            ]
            self.planning.artifact_updater(artifact_id, {
                "expectedVersion": cases[0].get("artifactVersion") or artifact.get("version"),
                "details": {"test_suite": {**suite, "test_cases": test_cases}},
            }, actor)


def _parent_id(payload: dict[str, Any]) -> str:
    lineage = _dict(payload.get("lineage"))
    return _text(payload.get("parentId") or payload.get("parent_id") or lineage.get("parentId") or lineage.get("parent_id") or payload.get("storyId") or lineage.get("storyId"))


def _child_summary(item: dict[str, Any]) -> dict[str, Any]:
    payload = _dict(item.get("payload"))
    confidence = _number(payload.get("confidence"))
    return {
        "id": _text(item.get("artifact_id")), "title": _text(item.get("title")),
        "description": _text(payload.get("description") or payload.get("purpose")),
        "status": _text(item.get("state")).title(), "confidence": int(round(confidence * 100)) if confidence <= 1 else int(confidence),
        "version": int(item.get("version") or 1), "editable": _text(item.get("state")).casefold() in {"draft", "review"},
    }


def _test_summary(case: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(case.get("id") or case.get("test_case_id") or artifact.get("artifact_id")),
        "title": _text(case.get("title") or case.get("name") or case.get("scenario")) or "Generated test",
        "description": _text(case.get("description") or case.get("steps") or case.get("expected_result")),
        "category": _text(case.get("category") or case.get("type")) or "Functional",
        "status": _text(artifact.get("state")).title(),
        "artifactId": _text(artifact.get("artifact_id")), "artifactVersion": int(artifact.get("version") or 1),
        "editable": _text(artifact.get("state")).casefold() in {"draft", "review"},
    }


def _estimate_summary(payload: dict[str, Any], story: dict[str, Any], persisted: dict[str, Any] | None = None) -> dict[str, Any]:
    estimate = _dict(payload.get("estimate") or payload.get("engineeringEstimate"))
    persisted_value = _dict(_dict(persisted).get("effectiveEstimate")) or _dict(persisted)
    estimate = {**persisted_value, **estimate}
    return {
        "engineeringDays": float(estimate.get("engineeringDays") or estimate.get("days") or 0),
        "engineeringHours": float(estimate.get("engineeringHours") or estimate.get("hours") or 0),
        "storyPoints": int(story.get("storyPoints") or estimate.get("storyPoints") or 0),
        "confidence": int(estimate.get("confidence") or story.get("confidence") or 0),
    }


def _latest_estimate(values: Any, story: dict[str, Any]) -> dict[str, Any]:
    identifiers = {_text(story.get("id")), _text(story.get("sourceItemId"))}
    matches = [
        item for item in _list(values)
        if isinstance(item, dict)
        and any(_text(item.get(key)) in identifiers for key in ("artifactId", "artifact_id", "workItemId"))
    ]
    return max(matches, key=lambda item: (int(item.get("version") or 0), _text(item.get("updatedAt"))), default={})


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
