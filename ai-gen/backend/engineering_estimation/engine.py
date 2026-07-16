"""Evidence-based standard engineering estimation for planning artifacts."""

from __future__ import annotations

import math
import re
import hashlib
import json
from copy import deepcopy
from typing import Any

from .models import estimation_record, now_iso
from .repository import EngineeringEstimationRepository


POINTS = (1, 2, 3, 5, 8, 13)
COMPLEXITY_ORDER = ("Very Low", "Low", "Medium", "High", "Very High")


class EngineeringEstimationEngine:
    """Deterministic estimator. Repository and memory are evidence, never invented facts."""

    def __init__(self, repository: EngineeringEstimationRepository, *, platform: Any | None = None, memory: Any | None = None, repository_intelligence: Any | None = None) -> None:
        self.repository = repository
        self.platform = platform
        self.memory = memory
        self.repository_intelligence = repository_intelligence

    def estimate(self, request: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        artifact = _artifact(request)
        previous = self.repository.latest(str(artifact.get("id") or artifact.get("artifactId") or ""))
        source_hash = _source_hash(request)
        if previous and previous.get("sourceHash") == source_hash and request.get("forceRecalculate") is not True:
            return previous
        result = self._build(artifact, request)
        record = estimation_record(
            artifact=artifact,
            result=result,
            version=int(previous.get("version") or 0) + 1 if previous else 1,
            parent_estimate_id=str(previous.get("estimateId") or "") if previous else "",
        )
        record["sourceHash"] = source_hash
        record["correlationId"] = correlation_id
        self.repository.save(record)
        self._event("EngineeringEstimateGenerated", record)
        return record

    def estimate_task(self, request: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        artifact = _artifact(request)
        artifact["type"] = "Task"
        return self.estimate({**request, "artifact": artifact}, correlation_id=correlation_id)

    def get(self, estimate_id: str) -> dict[str, Any]:
        value = self.repository.get(estimate_id)
        if not value:
            raise LookupError(f"Engineering estimate {estimate_id} was not found.")
        return value

    def summary(self, estimate_id: str) -> dict[str, Any]:
        value = self.get(estimate_id)
        effective = dict(value.get("effectiveEstimate") or {})
        return {
            "estimateId": value["estimateId"], "artifactId": value["artifactId"], "artifactType": value["artifactType"],
            "title": value["title"], "version": value["version"], "status": value["status"],
            "report": effective.get("report") or {}, "confidence": effective.get("confidence", 0),
            "risk": effective.get("risk", "Unknown"), "topEstimationDrivers": effective.get("topEstimationDrivers") or [],
            "isOverridden": bool(value.get("userEstimate")), "updatedAt": value["updatedAt"],
        }

    def recalculate(self, request: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        estimate_id = str(request.get("estimateId") or "")
        source = self.get(estimate_id)
        artifact = dict(request.get("artifact") or {}) or {
            "id": source["artifactId"], "type": source["artifactType"], "title": source["title"], "projectId": source.get("projectId"),
        }
        result = self.estimate({**request, "artifact": artifact, "forceRecalculate": True}, correlation_id=correlation_id)
        self._event("EngineeringEstimateUpdated", result)
        return result

    def override(self, estimate_id: str, request: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
        value = self.get(estimate_id)
        reason = str(request.get("overrideReason") or "").strip()
        if not reason:
            raise ValueError("overrideReason is required so the original estimate remains explainable.")
        user = {
            "engineeringHours": _positive(request.get("engineeringHours"), "engineeringHours"),
            "engineeringDays": round(_positive(request.get("engineeringHours"), "engineeringHours") / 8, 2),
            "storyPoints": int(_positive(request.get("storyPoints"), "storyPoints")),
            "estimatedSprintCount": float(request.get("estimatedSprintCount") or (value.get("effectiveEstimate") or {}).get("estimatedSprintCount") or 1),
            "overriddenBy": actor or str(request.get("actor") or "current-user"), "overriddenAt": now_iso(),
        }
        effective = deepcopy(value.get("originalEstimate") or {})
        effective.update(user)
        report = dict(effective.get("report") or {})
        report.update({"engineeringDays": user["engineeringDays"], "storyPoints": user["storyPoints"], "estimatedSprintCount": user["estimatedSprintCount"]})
        effective["report"] = report
        value.update({"status": "Overridden", "userEstimate": user, "effectiveEstimate": effective, "overrideReason": reason, "updatedAt": now_iso()})
        self.repository.save(value)
        self._event("EngineeringEstimateOverridden", value)
        return value

    def approve(self, estimate_id: str, actor: str = "") -> dict[str, Any]:
        value = self.get(estimate_id)
        value.update({"status": "Approved", "approvedBy": actor or "current-user", "approvedAt": now_iso(), "updatedAt": now_iso()})
        self.repository.save(value)
        self._event("EngineeringEstimateApproved", value)
        return value

    def learn(self, estimate_id: str, request: dict[str, Any]) -> dict[str, Any]:
        value = self.get(estimate_id)
        actual_hours = _positive(request.get("actualDurationHours"), "actualDurationHours")
        outcome = {
            "estimateId": estimate_id, "artifactId": value["artifactId"], "projectId": value.get("projectId", ""),
            "estimatedDurationHours": (value.get("effectiveEstimate") or {}).get("engineeringHours", 0),
            "estimatedStoryPoints": (value.get("effectiveEstimate") or {}).get("storyPoints", 0),
            "actualDurationHours": actual_hours, "actualStoryPoints": request.get("actualStoryPoints"),
            "actualCompletionDate": str(request.get("actualCompletionDate") or now_iso()),
            "developerOverride": bool(value.get("userEstimate")), "reviewCount": int(request.get("reviewCount") or 0),
            "prIterations": int(request.get("prIterations") or 0), "reopenedWork": int(request.get("reopenedWork") or 0),
            "regressionIssues": int(request.get("regressionIssues") or 0), "recordedAt": now_iso(),
        }
        self.repository.save_outcome(estimate_id, outcome)
        self._event("EngineeringEstimateLearned", outcome)
        return outcome

    def _build(self, artifact: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        repository = _mapping(request.get("repositoryIntelligence") or request.get("repositoryContext") or artifact.get("repositoryContext")) or self._repository_context(artifact)
        memory = _mapping(request.get("engineeringMemory") or request.get("memoryContext")) or self._memory_context(artifact, repository)
        criteria = _criteria(request.get("acceptanceCriteria") or artifact.get("acceptanceCriteria") or artifact.get("acceptance_criteria"))
        dependencies = _items(request.get("dependencyAnalysis") or artifact.get("dependencies"))
        risks = _items(request.get("riskAnalysis") or artifact.get("risks"))
        children = _children(request, artifact)
        kind = str(artifact.get("type") or artifact.get("artifactType") or "Story").title()

        task_artifacts = [item for item in children if _kind(item) == "Task"]
        if kind == "Task":
            task_artifacts = [artifact]
        elif kind == "Story" and not task_artifacts:
            task_artifacts = _decompose_story(artifact, criteria, repository, request)
        else:
            task_artifacts.extend(_descendants(children, "Task"))

        task_estimates = [self._task(item, criteria, repository, memory, dependencies, risks, request) for item in _dedupe(task_artifacts)]
        child_estimates = self._estimate_children(children, repository, memory, request)
        if not task_estimates and child_estimates:
            task_estimates = [task for child in child_estimates for task in child.get("taskEstimates") or []]
        if not task_estimates:
            task_estimates = [self._task({"id": f"{artifact.get('id', 'work')}-implementation", "type": "Task", "title": f"Implement {artifact.get('title') or 'approved scope'}", "description": artifact.get("description", "")}, criteria, repository, memory, dependencies, risks, request)]

        hours = round(sum(float(task["estimatedDurationHours"]) for task in task_estimates), 1)
        points = sum(int(task["storyPointContribution"]) for task in task_estimates)
        confidence = round(sum(float(task["confidence"]) * float(task["estimatedDurationHours"]) for task in task_estimates) / max(hours, 1))
        reuse = _reuse(repository, memory)
        risk = _risk_level(risks, task_estimates)
        tests = sum(int(task["estimatedTestCases"]) for task in task_estimates)
        prs = max(1, math.ceil(len(task_estimates) / 3))
        days = round(hours / 8, 1)
        suggested_team = 1 if days <= 5 else 2 if days <= 25 else 3 if days <= 60 else 4
        sprints = max(1, round(days / max(10 * suggested_team, 1), 1))
        drivers = _drivers(repository, memory, dependencies, risks, criteria, task_estimates)
        high_risk_stories = sum(1 for child in child_estimates if child.get("artifactType") == "Story" and child.get("risk") in {"High", "Critical"})
        if kind == "Story" and risk in {"High", "Critical"}:
            high_risk_stories = 1
        report = {
            "epic": artifact.get("title") if kind == "Epic" else "",
            "features": sum(1 for item in children if _kind(item) == "Feature"),
            "stories": sum(1 for item in children if _kind(item) == "Story") + sum(1 for item in _descendants(children, "Story")),
            "tasks": len(task_estimates), "engineeringDays": days, "storyPoints": points,
            "estimatedSprintCount": sprints, "averageStorySize": round(points / max(1, sum(1 for item in children if _kind(item) == "Story") or (1 if kind == "Story" else 0)), 1),
            "confidence": confidence, "risk": risk, "repositoryReuse": reuse,
            "estimatedTestCases": tests, "estimatedPullRequests": prs, "highRiskStories": high_risk_stories,
            "suggestedTeamSize": suggested_team,
        }
        return {
            "artifactType": kind, "engineeringHours": hours, "engineeringDays": days, "storyPoints": points,
            "complexity": _aggregate_complexity(task_estimates), "confidence": confidence, "risk": risk,
            "taskCount": len(task_estimates), "dependencyCount": len(dependencies), "estimatedTestCases": tests,
            "estimatedPullRequests": prs, "estimatedSprintCount": sprints, "suggestedTeamSize": suggested_team,
            "repositoryImpact": _repository_impact(repository), "repositoryReuse": reuse,
            "repositorySnapshot": str(repository.get("snapshotId") or repository.get("repositorySnapshotVersion") or ""),
            "taskEstimates": task_estimates, "childEstimates": child_estimates,
            "topEstimationDrivers": drivers, "report": report,
            "reasoning": _reasoning(confidence, risk, reuse, repository, memory, criteria),
            "warnings": _warnings(repository, criteria, memory),
        }

    def _task(self, task: dict[str, Any], criteria: list[str], repository: dict[str, Any], memory: dict[str, Any], dependencies: list[Any], risks: list[Any], request: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(str(task.get(key) or "") for key in ("title", "description", "objective", "implementationArea")).lower()
        factor = 1
        factor += min(4, len(_items(task.get("dependencies"))) + len(dependencies))
        factor += 2 if re.search(r"database|migration|schema|persistence", text) else 0
        factor += 2 if re.search(r"authentication|authorization|permission|security", text) else 0
        factor += 2 if re.search(r"external api|integration|third.party", text) else 0
        factor += 1 if re.search(r"telemetry|logging|observability|performance", text) else 0
        factor += 1 if len(criteria) >= 5 else 0
        new_components = _count(repository.get("newComponents") or request.get("newComponents"))
        existing = _count(repository.get("existingComponents") or repository.get("relevantFiles") or repository.get("files"))
        factor += min(3, new_components)
        factor -= 1 if existing else 0
        factor -= 1 if _memory_count(memory) else 0
        factor = max(1, factor)
        complexity = COMPLEXITY_ORDER[min(4, max(0, math.ceil(factor / 3) - 1))]
        hours = max(2, round((2.5 + factor * 1.75) * (0.85 if existing else 1), 1))
        points = _points(hours)
        confidence = 64
        evidence: list[dict[str, Any]] = []
        if repository:
            confidence += 10
            evidence.append({"type": "Repository", "statement": "Repository Intelligence context was supplied.", "source": "Repository Intelligence"})
        else:
            confidence -= 15
        if existing:
            confidence += 8
            evidence.append({"type": "Reuse", "statement": f"{existing} reusable repository item(s) were supplied.", "source": "Repository Intelligence"})
        if criteria:
            confidence += min(10, len(criteria) * 2)
            evidence.append({"type": "Acceptance", "statement": f"{len(criteria)} acceptance criterion/criteria constrain the estimate.", "source": "Planning Package"})
        else:
            confidence -= 12
        memory_count = _memory_count(memory)
        if memory_count:
            confidence += min(8, memory_count * 2)
            evidence.append({"type": "Memory", "statement": f"{memory_count} relevant approved memory match(es) support the estimate.", "source": "Engineering Memory"})
        if dependencies:
            confidence -= min(10, len(dependencies) * 2)
            evidence.append({"type": "Dependency", "statement": f"{len(dependencies)} dependency/dependencies increase coordination effort.", "source": "Dependency Analysis"})
        if risks:
            confidence -= min(10, len(risks) * 2)
        confidence = max(25, min(98, confidence))
        test_cases = max(1, math.ceil(max(1, len(criteria)) * (1.2 if re.search(r"test|qa|validation", text) else .6)))
        return {
            "taskId": str(task.get("id") or task.get("taskId") or ""), "taskName": str(task.get("title") or "Implementation Task"),
            "description": str(task.get("description") or task.get("objective") or ""), "estimatedDurationHours": hours,
            "estimatedDuration": f"{hours:g} hours", "storyPointContribution": points, "complexity": complexity,
            "confidence": confidence, "engineeringEvidence": evidence,
            "dependencies": _items(task.get("dependencies")) or dependencies, "risk": _risk_level(risks, []),
            "reasoning": _task_reason(existing, memory_count, criteria, dependencies, factor), "estimatedTestCases": test_cases,
        }

    def _estimate_children(self, children: list[dict[str, Any]], repository: dict[str, Any], memory: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
        output = []
        for child in children:
            if _kind(child) not in {"Feature", "Story"}:
                continue
            nested = self._build(child, {**request, "artifact": child, "children": _children({}, child), "repositoryContext": repository, "memoryContext": memory})
            output.append({"artifactId": str(child.get("id") or ""), "artifactType": _kind(child), "title": child.get("title"), **nested})
        return output

    def _event(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.platform:
            return
        try:
            self.platform.events.publish({"eventType": event_type, "source": "EngineeringEstimation", "projectId": payload.get("projectId"), "correlationId": payload.get("correlationId"), "payload": {"estimateId": payload.get("estimateId"), "artifactId": payload.get("artifactId"), "status": payload.get("status")}})
        except (OSError, ValueError, TypeError):
            return

    def _repository_context(self, artifact: dict[str, Any]) -> dict[str, Any]:
        if not self.repository_intelligence:
            return {}
        try:
            repositories = list((self.repository_intelligence.list_repositories() or {}).get("repositories") or [])
            project_id = str(artifact.get("projectId") or artifact.get("project_id") or "")
            selected = next((item for item in repositories if str(item.get("projectId") or (item.get("metadata") or {}).get("projectId") or "") == project_id), None)
            if selected is None and len(repositories) == 1:
                selected = repositories[0]
            if not selected:
                return {}
            repository_id = str(selected.get("repositoryId") or "")
            snapshot = self.repository_intelligence.get_current_snapshot(repository_id) or {}
            graph = self.repository_intelligence.get_graph(repository_id) or {}
            nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
            files = [item for item in nodes if str(item.get("type") or "").casefold() == "file"]
            return {
                "mode": "CodeIndexed" if snapshot else "Unavailable", "repositoryId": repository_id,
                "snapshotId": snapshot.get("snapshotId") or selected.get("latestSnapshotId"),
                "health": selected.get("status") or selected.get("latestScanStatus") or "Unknown",
                "modules": snapshot.get("modules") or [], "existingComponents": len(nodes),
                "relevantFiles": files, "graphStatus": selected.get("graphStatus") or "NotConnected",
            }
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def _memory_context(self, artifact: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
        if not self.memory:
            return {}
        try:
            result = self.memory.find_relevant_memory({
                "projectId": artifact.get("projectId") or artifact.get("project_id") or "",
                "query": [artifact.get("title"), artifact.get("description")],
                "artifactType": artifact.get("type") or artifact.get("artifactType"),
                "modules": repository.get("modules") or [], "limit": 5,
            })
            values = result.get("results") or result.get("memories") or []
            approved = [item for item in values if str(item.get("approvalStatus") or item.get("status") or "").casefold() in {"approved", "indexed", "available"}]
            return {"matches": approved, "count": len(approved), "source": "Engineering Memory"}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}


def _artifact(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("artifact") or request.get("planningPackage") or request.get("requirement") or {}
    if not isinstance(value, dict) or not (value.get("title") or value.get("id") or value.get("artifactId")):
        raise ValueError("artifact or planningPackage is required for engineering estimation.")
    return dict(value)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    if isinstance(value, list): return [item for item in value if item not in (None, "")]
    if isinstance(value, dict): return [dict(value)] if value else []
    return [value] if value not in (None, "") else []


def _criteria(value: Any) -> list[str]:
    result = []
    for item in _items(value):
        text = str(item.get("text") or item.get("title") or item.get("description") or "") if isinstance(item, dict) else str(item)
        if text.strip() and text.strip() not in result: result.append(text.strip())
    return result


def _children(request: dict[str, Any], artifact: dict[str, Any]) -> list[dict[str, Any]]:
    values = request.get("children") or artifact.get("children") or []
    for key in ("features", "stories", "tasks"):
        values = [*_items(values), *_items(artifact.get(key))]
    return [dict(item) for item in _items(values) if isinstance(item, dict)]


def _kind(value: dict[str, Any]) -> str:
    return str(value.get("type") or value.get("artifactType") or value.get("workItemType") or "").title()


def _descendants(values: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    output = []
    for value in values:
        nested = _children({}, value)
        output.extend(item for item in nested if _kind(item) == kind)
        output.extend(_descendants(nested, kind))
    return output


def _dedupe(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        key = str(value.get("id") or value.get("taskId") or value.get("title") or index)
        output[key] = value
    return list(output.values())


def _decompose_story(artifact: dict[str, Any], criteria: list[str], repository: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    title = str(artifact.get("title") or "Story")
    text = " ".join([title, str(artifact.get("description") or ""), *criteria, str(request.get("technologyStack") or "")]).lower()
    tasks = []
    if re.search(r"api|backend|service|controller|repository|endpoint", text):
        tasks.append({"id": f"{artifact.get('id', 'story')}-backend", "type": "Task", "title": f"Implement backend support for {title}", "description": "Implement the approved server-side acceptance scope."})
    if re.search(r"ui|screen|dashboard|frontend|mobile|view|display", text):
        tasks.append({"id": f"{artifact.get('id', 'story')}-ui", "type": "Task", "title": f"Implement user experience for {title}", "description": "Implement the approved user-facing acceptance scope."})
    if re.search(r"database|data|schema|migration|persistence", text):
        tasks.append({"id": f"{artifact.get('id', 'story')}-data", "type": "Task", "title": f"Implement data changes for {title}", "description": "Implement the approved data and persistence scope."})
    if not tasks:
        tasks.append({"id": f"{artifact.get('id', 'story')}-implementation", "type": "Task", "title": f"Implement {title}", "description": "Implement the approved acceptance scope using existing repository patterns where available."})
    tasks.append({"id": f"{artifact.get('id', 'story')}-tests", "type": "Task", "title": f"Validate {title}", "description": "Add tests mapped to the approved acceptance criteria."})
    if re.search(r"documentation|runbook|readme|operator guide", text):
        tasks.append({"id": f"{artifact.get('id', 'story')}-docs", "type": "Task", "title": f"Document {title}", "description": "Update the required engineering documentation."})
    return tasks


def _count(value: Any) -> int:
    if isinstance(value, (list, tuple, set, dict)): return len(value)
    try: return int(value or 0)
    except (TypeError, ValueError): return 0


def _memory_count(value: dict[str, Any]) -> int:
    return _count(value.get("matches") or value.get("relevantMemories") or value.get("results"))


def _reuse(repository: dict[str, Any], memory: dict[str, Any]) -> int:
    explicit = repository.get("reusePercentage") or repository.get("reuseScore")
    if explicit is not None:
        try: return max(0, min(100, round(float(explicit))))
        except (TypeError, ValueError): pass
    existing = _count(repository.get("existingComponents") or repository.get("relevantFiles") or repository.get("files"))
    new = _count(repository.get("newComponents"))
    memory_matches = _memory_count(memory)
    return min(90, round(100 * (existing + memory_matches) / max(1, existing + memory_matches + new + 2)))


def _points(hours: float) -> int:
    target = 1 if hours <= 4 else 2 if hours <= 8 else 3 if hours <= 16 else 5 if hours <= 28 else 8 if hours <= 48 else 13
    return min(POINTS, key=lambda value: abs(value - target))


def _risk_level(risks: list[Any], tasks: list[dict[str, Any]]) -> str:
    score = len(risks) + sum(1 for task in tasks if task.get("complexity") in {"High", "Very High"})
    return "Critical" if score >= 7 else "High" if score >= 3 else "Medium" if score >= 1 else "Low"


def _aggregate_complexity(tasks: list[dict[str, Any]]) -> str:
    average = sum(COMPLEXITY_ORDER.index(str(task.get("complexity") or "Medium")) for task in tasks) / max(1, len(tasks))
    return COMPLEXITY_ORDER[min(4, max(0, round(average)))]


def _repository_impact(repository: dict[str, Any]) -> dict[str, Any]:
    mode = str(repository.get("mode") or repository.get("repositoryMode") or ("CodeIndexed" if repository else "Unavailable"))
    modules = _items(repository.get("affectedModules") or repository.get("modules"))
    files = _items(repository.get("relevantFiles") or repository.get("files"))
    return {"mode": mode, "affectedModules": modules, "relevantFileCount": len(files), "repositoryHealth": repository.get("health") or "Unknown"}


def _drivers(repository: dict[str, Any], memory: dict[str, Any], dependencies: list[Any], risks: list[Any], criteria: list[str], tasks: list[dict[str, Any]]) -> list[str]:
    drivers = []
    existing = _count(repository.get("existingComponents") or repository.get("relevantFiles") or repository.get("files"))
    new = _count(repository.get("newComponents"))
    if new: drivers.append(f"{new} new repository component(s) require implementation")
    if existing: drivers.append(f"{existing} existing repository item(s) may be reused")
    if dependencies: drivers.append(f"{len(dependencies)} dependency/dependencies require coordination")
    if risks: drivers.append(f"{len(risks)} engineering risk signal(s) affect contingency")
    if criteria: drivers.append(f"{len(criteria)} acceptance criterion/criteria define verification scope")
    if _memory_count(memory): drivers.append(f"{_memory_count(memory)} approved Engineering Memory match(es) provide precedent")
    if any(task.get("complexity") in {"High", "Very High"} for task in tasks): drivers.append("High-complexity implementation work increases engineering and review effort")
    if not repository: drivers.append("Repository context is unavailable, reducing estimate confidence")
    return drivers[:8]


def _reasoning(confidence: int, risk: str, reuse: int, repository: dict[str, Any], memory: dict[str, Any], criteria: list[str]) -> list[str]:
    return [
        f"Confidence is {confidence}% based on {'available' if repository else 'missing'} repository evidence.",
        f"Risk is {risk} after dependency, scope, and task-complexity adjustment.",
        f"Repository and approved-memory reuse is estimated at {reuse}% from supplied evidence.",
        f"Verification effort is grounded in {len(criteria)} acceptance criterion/criteria.",
        f"Engineering Memory contributed {_memory_count(memory)} approved match(es) as supporting evidence.",
    ]


def _warnings(repository: dict[str, Any], criteria: list[str], memory: dict[str, Any]) -> list[str]:
    warnings = []
    if not repository: warnings.append("Repository Intelligence is unavailable; confidence was reduced and no code evidence was invented.")
    if not criteria: warnings.append("Acceptance criteria are missing; verification scope requires review.")
    if not _memory_count(memory): warnings.append("No similar approved Engineering Memory was available for calibration.")
    return warnings


def _task_reason(existing: int, memory: int, criteria: list[str], dependencies: list[Any], factor: int) -> list[str]:
    values = [f"Complexity factor {factor} reflects explicit implementation signals."]
    values.append(f"{existing} repository item(s) are available for reuse." if existing else "No reusable repository item was supplied.")
    values.append(f"{len(criteria)} acceptance criterion/criteria define expected validation.")
    if dependencies: values.append(f"{len(dependencies)} dependency/dependencies add coordination effort.")
    if memory: values.append(f"{memory} approved memory match(es) reduce uncertainty.")
    return values


def _positive(value: Any, name: str) -> float:
    try: number = float(value)
    except (TypeError, ValueError): raise ValueError(f"{name} must be a positive number.") from None
    if number <= 0: raise ValueError(f"{name} must be a positive number.")
    return number


def _source_hash(request: dict[str, Any]) -> str:
    payload = {key: value for key, value in request.items() if key not in {"estimateId", "forceRecalculate", "actor", "correlationId"}}
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
