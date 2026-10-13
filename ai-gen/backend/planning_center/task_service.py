"""Task generation and lifecycle operations for the Story planning workspace."""

from __future__ import annotations

from typing import Any, Callable


TASK_CATEGORIES = (
    "Frontend",
    "Backend",
    "Database",
    "API",
    "Testing",
    "Documentation",
    "Deployment",
    "Infrastructure",
)
TASK_PRIORITIES = ("Critical", "High", "Medium", "Low")
TASK_STATUSES = ("To Do", "In Progress", "Blocked", "Done")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    result: list[str] = []
    for item in _list(value):
        text = _text(item.get("title") or item.get("name")) if isinstance(item, dict) else _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def infer_task_category(value: dict[str, Any]) -> str:
    explicit = _text(value.get("category") or value.get("taskCategory"))
    work_area = _text(value.get("work_area") or value.get("workArea"))
    aliases = {
        "ui work": "Frontend", "frontend work": "Frontend", "backend work": "Backend",
        "data work": "Database", "analytics work": "Backend", "qa work": "Testing",
    }
    candidate = aliases.get(explicit.casefold()) or aliases.get(work_area.casefold()) or explicit
    if candidate in TASK_CATEGORIES:
        return candidate
    context = " ".join([_text(value.get("title")), _text(value.get("description")), work_area]).casefold()
    rules = (
        ("API", (" api", "endpoint", "route", "controller")),
        ("Testing", ("test", "qa ", "validate", "verification")),
        ("Database", ("database", "schema", "migration", "repository", "persist", "data field")),
        ("Frontend", ("frontend", "screen", "view", "component", " ui ")),
        ("Documentation", ("document", "readme", "runbook")),
        ("Deployment", ("deploy", "release", "pipeline")),
        ("Infrastructure", ("infrastructure", "terraform", "cloud", "environment")),
    )
    return next((category for category, tokens in rules if any(token in f" {context}" for token in tokens)), "Backend")


def normalize_task_details(value: dict[str, Any], *, source: str = "manual") -> dict[str, Any]:
    estimate_value = value.get("estimate")
    estimate = _dict(estimate_value)
    hours = _number(estimate.get("engineeringHours") or estimate.get("hours") or value.get("estimateHours"))
    days = _number(estimate.get("engineeringDays") or estimate.get("days"))
    if not hours and days:
        hours = days * 8
    if not days and hours:
        days = hours / 8
    priority = _text(value.get("priority")).title() or "Medium"
    task_status = _text(value.get("taskStatus") or value.get("workStatus") or value.get("deliveryStatus")).title() or "To Do"
    return {
        "description": _text(value.get("description") or value.get("purpose")),
        "category": infer_task_category(value),
        "estimate": {
            "engineeringHours": round(hours, 2),
            "engineeringDays": round(days, 2),
            "confidence": int(_number(estimate.get("confidence") or value.get("estimateConfidence"))),
        },
        "owner": _text(value.get("owner")) or "Unassigned",
        "priority": priority if priority in TASK_PRIORITIES else "Medium",
        "taskStatus": task_status if task_status in TASK_STATUSES else "To Do",
        "dependencies": _strings(value.get("dependencies")),
        "acceptanceCriteria": _strings(value.get("acceptanceCriteria") or value.get("acceptance_criteria")),
        "risks": _strings(value.get("risks")),
        "source": _text(value.get("source")) or source,
    }


def task_summary(item: dict[str, Any]) -> dict[str, Any]:
    payload = _dict(item.get("payload"))
    details = normalize_task_details({**payload, "title": item.get("title")}, source=_text(payload.get("source")) or "ai")
    confidence = _number(payload.get("confidence"))
    return {
        "id": _text(item.get("artifact_id")),
        "title": _text(item.get("title")),
        **details,
        "status": _text(item.get("state")).title(),
        "artifactStatus": _text(item.get("state")).title(),
        "confidence": int(round(confidence * 100)) if confidence <= 1 else int(confidence),
        "version": int(item.get("version") or 1),
        "editable": _text(item.get("state")).casefold() in {"draft", "review"},
    }


class TaskGenerationService:
    """Creates and changes Task artifacts without creating a second task store."""

    def __init__(
        self,
        *,
        planning_service: Any,
        artifact_provider: Callable[[], dict[str, Any]],
        ai_task_generator: Callable[[str, str], dict[str, Any]],
    ) -> None:
        self.planning = planning_service
        self.artifact_provider = artifact_provider
        self.ai_task_generator = ai_task_generator

    def create_for_story(self, story_id: str, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        story = self.planning.get(story_id)
        if story.get("type") != "Story":
            raise ValueError(f"Planning item {story_id} is not a Story.")
        mode = _text(request.get("mode") or request.get("source") or "manual").casefold()
        if mode in {"ai", "generate", "regenerate"}:
            generation = self.ai_task_generator(story_id, actor)
            return {"storyId": story_id, "mode": "ai", "generation": generation, "tasks": self.list_for_story(story_id)}
        if mode != "manual":
            raise ValueError("Task mode must be manual or ai.")
        if not self.planning.artifact_creator:
            raise ValueError("Manual Task creation is not available.")
        candidates = request.get("tasks") if isinstance(request.get("tasks"), list) else [request]
        created = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            title = _text(candidate.get("title"))
            if not title:
                raise ValueError("Task title is required.")
            details = normalize_task_details(candidate, source="manual")
            created.append(self.planning.artifact_creator({
                "artifact_type": "Task", "state": "draft", "title": title,
                "source_item": {"id": story_id, "type": "Story", "title": story.get("title")},
                "created_by": actor or "HEI User", "payload": {"parentId": story_id, **details},
            }))
        return {
            "storyId": story_id, "mode": "manual", "createdCount": len(created),
            "tasks": [task_summary(item) for item in created], "allTasks": self.list_for_story(story_id),
        }

    def update(self, task_id: str, request: dict[str, Any], actor: str = "") -> dict[str, Any]:
        action = _text(request.get("action") or "edit").casefold()
        if action == "regenerate":
            self.planning.regenerate_node({"nodeId": task_id}, actor)
            return {"action": action, "task": self.get_task(task_id)}
        if action == "split":
            result = self.planning.update_node({
                "nodeId": task_id, "action": "split", "titles": request.get("titles"),
                "archiveOriginal": request.get("archiveOriginal", True),
            }, actor)
            return {**result, "tasks": [self.get_task(node["id"]) for node in result.get("nodes", [])]}
        if action == "merge":
            result = self.planning.update_node({
                "nodeId": task_id, "action": "merge", "nodeIds": request.get("taskIds") or request.get("nodeIds"),
                "title": request.get("title"),
            }, actor)
            return {**result, "task": self.get_task(_dict(result.get("node")).get("id"))}
        if action != "edit":
            raise ValueError(f"Unsupported Task action: {action}.")
        current = self._artifact(task_id)
        if _text(current.get("state")).casefold() not in {"draft", "review"}:
            raise ValueError("Only Draft or Review Tasks can be edited.")
        payload = _dict(current.get("payload"))
        details = normalize_task_details({**payload, **request}, source=_text(payload.get("source")) or "manual")
        for key in ("generatedUsing", "work_item_dna", "validationReport", "confidence"):
            if key in payload:
                details[key] = payload[key]
        self.planning.artifact_updater(task_id, {
            "expectedVersion": request.get("expectedVersion", current.get("version")),
            "title": request.get("title", current.get("title")),
            "description": details["description"], "details": details,
        }, actor)
        return {"action": "edit", "task": self.get_task(task_id)}

    def delete(self, task_id: str, actor: str = "") -> dict[str, Any]:
        return self.planning.delete_node({"nodeId": task_id, "cascade": False}, actor)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return task_summary(self._artifact(task_id))

    def list_for_story(self, story_id: str) -> list[dict[str, Any]]:
        return [
            task_summary(item) for item in self._artifacts()
            if "task" in _text(item.get("artifact_type")).casefold()
            and _parent_id(_dict(item.get("payload"))) == story_id
            and _text(item.get("state")).casefold() != "archived"
        ]

    def _artifact(self, task_id: str) -> dict[str, Any]:
        item = next((item for item in self._artifacts() if _text(item.get("artifact_id")) == task_id), None)
        if not item or "task" not in _text(item.get("artifact_type")).casefold():
            raise LookupError(f"Task {task_id} was not found.")
        return item

    def _artifacts(self) -> list[dict[str, Any]]:
        return [item for item in _list(self.artifact_provider().get("artifacts")) if isinstance(item, dict)]


def _parent_id(payload: dict[str, Any]) -> str:
    lineage = _dict(payload.get("lineage"))
    return _text(payload.get("parentId") or payload.get("parent_id") or lineage.get("parentId") or lineage.get("parent_id") or payload.get("storyId"))
