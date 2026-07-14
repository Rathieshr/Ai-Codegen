"""Read-only sprint flow intelligence over the centralized Azure DevOps cache."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any, Callable

from backend.platform_sdk import as_azure_devops_sdk

from .service import WorkItemNotFoundError
from .sprint_models import SprintIntelligenceReport
from .sprint_repository import SprintIntelligenceRepository


COMPLETED_STATES = {"closed", "completed", "done", "resolved", "removed"}
ACTIVE_STATES = {"active", "committed", "in progress", "doing"}
FAILED_BUILD_RESULTS = {"failed", "partiallysucceeded", "canceled", "cancelled"}


class SprintIntelligenceService:
    def __init__(self, *, azure_devops: Any, repository: SprintIntelligenceRepository, estimation: Any | None = None, platform: Any | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.ado_sdk, self.repository, self.estimation, self.platform = as_azure_devops_sdk(azure_devops), repository, estimation, platform
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def current(self, project_id: str, team_id: str = "") -> dict[str, Any]:
        iteration = self._current_iteration(project_id, team_id)
        return self.report(project_id, str(iteration["iterationId"]), team_id=team_id)

    def report(self, project_id: str, iteration_id: str, *, team_id: str = "") -> dict[str, Any]:
        now = _utc(self.clock())
        iteration = self._iteration(project_id, iteration_id)
        items = self._iteration_items(project_id, iteration, team_id)
        pull_requests = list(self.ado_sdk.cached_collection(project_id, "pullRequests").values())
        builds = list(self.ado_sdk.cached_collection(project_id, "builds").values())
        start = _date(iteration.get("startDate"))
        finish = _date(iteration.get("finishDate"))
        completed = [item for item in items if _complete(item)]
        remaining = [item for item in items if not _complete(item)]
        planned_scope = _scope(items)
        completed_scope = _scope(completed)
        remaining_scope = _scope(remaining)
        carryover = [item for item in items if start and (_date(item.get("createdAt")) or start) < start and (_date(item.get("sprintAddedAt")) or start) <= start]
        blockers = _blockers(remaining)
        aging = _aging(remaining, now.date())
        prs = _pr_metrics(pull_requests, {str(item.get("workItemId")) for item in items}, now)
        build_metrics = _build_metrics(builds, start, finish)
        estimate_accuracy = self.estimation.accuracy(project_id, team_id, include_items=False) if self.estimation else _uncalibrated(project_id, team_id)
        burndown = _burndown(items, start, finish, now.date())
        velocity = self._velocity(project_id, iteration, completed_scope)
        forecast = _forecast(start, finish, now.date(), completed_scope, remaining_scope, items)
        confidence = _confidence(items, iteration, burndown, estimate_accuracy, forecast)
        risks = _risks(items, remaining, iteration, start, finish, now.date(), blockers, aging, prs, build_metrics)
        health = _health(items, remaining, risks, forecast, finish, now.date())
        report = SprintIntelligenceReport(
            report_id=_report_id(project_id, iteration_id, items, now), project_id=project_id,
            iteration_id=str(iteration_id), iteration=iteration, health=health,
            completion_confidence=confidence, forecast=forecast,
            metrics={
                "plannedScope": planned_scope, "completedScope": completed_scope, "remainingScope": remaining_scope,
                "velocity": velocity, "carryover": _work_summary(carryover), "blockedWork": _work_summary([entry["item"] for entry in blockers]),
                "agingWork": _work_summary([entry["item"] for entry in aging]), "pullRequestWaitingTime": prs,
                "buildFailures": build_metrics, "reopenedWork": {"itemCount": sum(1 for item in items if int(item.get("reopenCount") or 0) > 0), "reopenCount": sum(int(item.get("reopenCount") or 0) for item in items)},
                "estimateAccuracy": estimate_accuracy, "completionForecast": forecast,
                "capacity": _capacity(iteration, planned_scope),
            },
            burndown_series=burndown, current_blockers=[_blocker_public(entry) for entry in blockers],
            delivery_risks=risks, recommended_interventions=_interventions(risks),
            evidence=_evidence(project_id, iteration, items, pull_requests, builds, estimate_accuracy),
            privacy={
                "mode": "EngineeringFlowOnly", "individualRanking": False,
                "excludedMetrics": ["commitsByDeveloper", "linesOfCodeByDeveloper", "keyboardActivity", "hoursOnline"],
                "message": "HEI evaluates delivery flow and bottlenecks, not individual developer productivity.",
            }, generated_at=now.isoformat(),
        ).to_dict()
        saved = self.repository.save(report)
        self._event("SprintIntelligenceGenerated", saved)
        return saved

    def burndown(self, project_id: str, iteration_id: str, *, team_id: str = "") -> dict[str, Any]:
        report = self.report(project_id, iteration_id, team_id=team_id)
        return {"projectId": project_id, "iterationId": iteration_id, "series": report["burndownSeries"], "scope": report["metrics"]["plannedScope"], "generatedAt": report["generatedAt"]}

    def risks(self, project_id: str, iteration_id: str, *, team_id: str = "") -> dict[str, Any]:
        report = self.report(project_id, iteration_id, team_id=team_id)
        return {"projectId": project_id, "iterationId": iteration_id, "health": report["health"], "risks": report["deliveryRisks"], "blockers": report["currentBlockers"], "recommendedInterventions": report["recommendedInterventions"], "generatedAt": report["generatedAt"]}

    def _current_iteration(self, project_id: str, team_id: str) -> dict[str, Any]:
        values = list(self.ado_sdk.cached_collection(project_id, "iterations").values())
        current = next((item for item in values if str(item.get("timeFrame") or "").lower() == "current" and (not team_id or not item.get("teamId") or str(item.get("teamId")) == team_id)), None)
        if not current:
            today = _utc(self.clock()).date()
            current = next((item for item in values if (_date(item.get("startDate")) or date.max) <= today <= (_date(item.get("finishDate")) or date.min)), None)
        if not current:
            raise WorkItemNotFoundError(f"Current sprint for project {project_id}")
        return current

    def _iteration(self, project_id: str, iteration_id: str) -> dict[str, Any]:
        value = self.ado_sdk.cached_collection(project_id, "iterations").get(str(iteration_id))
        if not isinstance(value, dict):
            raise WorkItemNotFoundError(f"Sprint {iteration_id} in project {project_id}")
        return dict(value)

    def _iteration_items(self, project_id: str, iteration: dict[str, Any], team_id: str) -> list[dict[str, Any]]:
        identities = {str(iteration.get(key) or "").strip().lower() for key in ("iterationId", "path", "name")}
        identities.discard("")
        histories = self.ado_sdk.cached_collection(project_id, "workItemRevisions")
        result = []
        for item in self.ado_sdk.cached_collection(project_id, "workItems").values():
            if str(item.get("iterationPath") or "").strip().lower() not in identities or (team_id and item.get("teamId") and str(item.get("teamId")) != team_id):
                continue
            value = dict(item)
            history = histories.get(str(item.get("workItemId"))) if isinstance(histories, dict) else None
            value["sprintAddedAt"] = _sprint_added_at(history, identities) or value.get("createdAt")
            result.append(value)
        return result

    def _velocity(self, project_id: str, iteration: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        current_path = str(iteration.get("path") or iteration.get("name") or "").lower()
        groups: dict[str, float] = {}
        for item in self.ado_sdk.cached_collection(project_id, "workItems").values():
            path = str(item.get("iterationPath") or "").lower()
            if path and path != current_path and _complete(item):
                groups[path] = groups.get(path, 0.0) + _points(item)
        values = list(groups.values())
        return {"currentCompletedStoryPoints": current["storyPoints"], "historicalAverageStoryPoints": round(mean(values), 1) if values else None, "historicalSprintCount": len(values), "status": "Calibrated" if len(values) >= 3 else "SparseHistory"}

    def _event(self, event_type: str, report: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "AzureDevOps", "projectId": report["projectId"], "correlationId": f"sprint-{report['reportId']}", "payload": {"reportId": report["reportId"], "iterationId": report["iterationId"], "health": report["health"]}})


def _scope(items: list[dict[str, Any]]) -> dict[str, Any]:
    estimated = [item for item in items if _estimate(item) is not None]
    return {"itemCount": len(items), "storyPoints": round(sum(_points(item) for item in items), 1), "estimatedItemCount": len(estimated), "unestimatedItemCount": len(items) - len(estimated)}


def _capacity(iteration: dict[str, Any], planned: dict[str, Any]) -> dict[str, Any]:
    value = _number(iteration.get("capacityStoryPoints"))
    if value is None:
        return {"available": False, "storyPoints": None, "plannedStoryPoints": planned["storyPoints"], "status": "NotEvaluated", "reason": "Team capacity is not available in the synchronized iteration context."}
    return {"available": True, "storyPoints": value, "plannedStoryPoints": planned["storyPoints"], "status": "Exceeded" if planned["storyPoints"] > value else "WithinCapacity", "reason": "Comparison uses configured sprint capacity and current synchronized scope."}


def _work_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"itemCount": len(items), "storyPoints": round(sum(_points(item) for item in items), 1), "workItemIds": [str(item.get("workItemId")) for item in items]}


def _blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        tags = {str(tag).lower() for tag in item.get("tags") or []}
        state = str(item.get("state") or "").lower()
        dependency = next((link for link in item.get("links") or [] if "dependency" in str(link.get("relation") or link.get("rel") or "").lower()), None)
        reasons = []
        if "blocked" in tags or state == "blocked": reasons.append("Work item is marked blocked.")
        if dependency: reasons.append("A dependency relationship requires resolution.")
        if reasons: result.append({"item": item, "reasons": reasons})
    return result


def _aging(items: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    result = []
    for item in items:
        changed = _date(item.get("changedAt") or item.get("stateChangeDate") or item.get("activatedAt") or item.get("createdAt"))
        age = max(0, (today - changed).days) if changed else 0
        if age >= 7: result.append({"item": item, "ageDays": age})
    return result


def _pr_metrics(prs: list[dict[str, Any]], work_ids: set[str], now: datetime) -> dict[str, Any]:
    relevant = [pr for pr in prs if not work_ids or work_ids & {str(value) for value in pr.get("linkedWorkItemIds") or []}]
    active = [pr for pr in relevant if str(pr.get("status") or "").lower() in {"active", "open", "notset"}]
    waits = [max(0.0, (now - _datetime(pr.get("creationDate"), now)).total_seconds() / 86400) for pr in active]
    return {"activePullRequests": len(active), "averageWaitingDays": round(mean(waits), 1) if waits else 0.0, "maximumWaitingDays": round(max(waits), 1) if waits else 0.0, "pullRequestIds": [str(pr.get("pullRequestId")) for pr in active]}


def _build_metrics(builds: list[dict[str, Any]], start: date | None, finish: date | None) -> dict[str, Any]:
    relevant = []
    for build in builds:
        when = _date(build.get("finishTime") or build.get("startTime") or build.get("queueTime"))
        if (not start or not when or when >= start) and (not finish or not when or when <= finish): relevant.append(build)
    failed = [build for build in relevant if str(build.get("result") or "").lower() in FAILED_BUILD_RESULTS]
    return {"failedCount": len(failed), "totalCount": len(relevant), "buildIds": [str(build.get("buildId")) for build in failed], "repeated": len(failed) >= 2}


def _burndown(items: list[dict[str, Any]], start: date | None, finish: date | None, today: date) -> list[dict[str, Any]]:
    if not start or not finish or finish < start: return []
    end = min(finish, max(start, today))
    total_days = max(1, (finish - start).days)
    final_scope = sum(_points(item) for item in items)
    result = []
    cursor = start
    while cursor <= end:
        visible = [item for item in items if (_date(item.get("sprintAddedAt") or item.get("createdAt")) or start) <= cursor]
        open_items = [item for item in visible if not (_date(item.get("closedAt")) and _date(item.get("closedAt")) <= cursor)]
        elapsed = min(total_days, (cursor - start).days)
        result.append({"date": cursor.isoformat(), "scopeStoryPoints": round(sum(_points(item) for item in visible), 1), "remainingStoryPoints": round(sum(_points(item) for item in open_items), 1), "remainingItemCount": len(open_items), "idealRemainingStoryPoints": round(max(0.0, final_scope * (1 - elapsed / total_days)), 1)})
        cursor += timedelta(days=1)
    return result


def _forecast(start, finish, today, completed, remaining, items) -> dict[str, Any]:
    if not items: return {"status": "InsufficientData", "forecastDate": None, "onTrack": None, "reason": "No sprint activity is synchronized."}
    if not remaining["itemCount"]: return {"status": "Completed", "forecastDate": today.isoformat(), "onTrack": True, "reason": "All synchronized sprint work is complete."}
    elapsed = max(1, (today - (start or today)).days + 1)
    completed_units = completed["storyPoints"] if completed["storyPoints"] > 0 else completed["itemCount"]
    remaining_units = remaining["storyPoints"] if completed["storyPoints"] > 0 else remaining["itemCount"]
    if completed_units <= 0: return {"status": "InsufficientData", "forecastDate": None, "onTrack": None, "reason": "No completed scope exists for a defensible forecast."}
    projected = today + timedelta(days=max(1, round(remaining_units / (completed_units / elapsed))))
    return {"status": "OnTrack" if finish and projected <= finish else "AtRisk", "forecastDate": projected.isoformat(), "onTrack": projected <= finish if finish else None, "reason": "Projection uses current completed scope per elapsed sprint day and is not a commitment."}


def _confidence(items, iteration, burndown, accuracy, forecast) -> dict[str, Any]:
    if not items: return {"score": 20, "level": "Low", "reasons": ["No synchronized sprint work is available."]}
    estimated_ratio = sum(_estimate(item) is not None for item in items) / len(items)
    score = 35 + 25 * estimated_ratio + (15 if iteration.get("startDate") and iteration.get("finishDate") else 0) + (10 if burndown else 0) + (10 if accuracy.get("accuracy") is not None else 0) + (5 if forecast.get("forecastDate") else 0)
    score = round(min(95, score))
    reasons = []
    if estimated_ratio < .7: reasons.append("Many sprint items do not have estimates.")
    if accuracy.get("accuracy") is None: reasons.append("Historical estimate calibration is sparse.")
    if forecast.get("forecastDate") is None: reasons.append("Completion history is insufficient for a date forecast.")
    return {"score": score, "level": "High" if score >= 80 else "Medium" if score >= 55 else "Low", "reasons": reasons or ["Synchronized scope, dates, and history support the forecast."]}


def _risks(items, remaining, iteration, start, finish, today, blockers, aging, prs, builds) -> list[dict[str, Any]]:
    risks = []
    active = [item for item in remaining if str(item.get("state") or "").lower() in ACTIVE_STATES]
    if len(active) > max(5, len(items) // 2): risks.append(_risk("TooMuchWorkInProgress", "High", f"{len(active)} work items are active concurrently.", [str(item.get("workItemId")) for item in active]))
    midpoint = start + timedelta(days=max(1, (finish - start).days // 2)) if start and finish else None
    late = [item for item in items if midpoint and (_date(item.get("sprintAddedAt") or item.get("createdAt")) or start) > midpoint]
    if late: risks.append(_risk("LateScopeAddition", "Medium", f"{len(late)} work item(s) entered after the sprint midpoint.", [str(item.get("workItemId")) for item in late]))
    if blockers: risks.append(_risk("BlockedDependency", "High", f"{len(blockers)} blocked or dependency-constrained work item(s) remain.", [str(entry["item"].get("workItemId")) for entry in blockers]))
    if prs["maximumWaitingDays"] >= 3: risks.append(_risk("PullRequestReviewBottleneck", "High" if prs["maximumWaitingDays"] >= 5 else "Medium", f"An active pull request has waited {prs['maximumWaitingDays']} days.", prs["pullRequestIds"]))
    tests_exist = any(str(item.get("workItemType") or "").lower() == "test case" for item in items)
    high_risk = [item for item in remaining if any(str(tag).lower() in {"high risk", "critical", "security"} for tag in item.get("tags") or [])]
    if high_risk and not tests_exist: risks.append(_risk("HighRiskUntestedWork", "High", "High-risk work has no synchronized Test Case in the sprint.", [str(item.get("workItemId")) for item in high_risk]))
    if builds["repeated"]: risks.append(_risk("RepeatedBuildFailures", "High", f"{builds['failedCount']} sprint builds failed or were cancelled.", builds["buildIds"]))
    large = [item for item in remaining if _points(item) >= 8 and str(item.get("workItemType") or "").lower() in {"user story", "product backlog item", "story"}]
    if large: risks.append(_risk("LargeUnfinishedStory", "Medium", f"{len(large)} large story or PBI remains unfinished.", [str(item.get("workItemId")) for item in large]))
    stale_tasks = [entry for entry in aging if str(entry["item"].get("workItemType") or "").lower() == "task"]
    if stale_tasks: risks.append(_risk("StaleTask", "Medium", f"{len(stale_tasks)} task(s) have not changed for at least seven days.", [str(entry["item"].get("workItemId")) for entry in stale_tasks]))
    capacity = _number(iteration.get("capacityStoryPoints"))
    planned = sum(_points(item) for item in items)
    if capacity is not None and planned > capacity: risks.append(_risk("CapacityMismatch", "High", f"Planned scope is {planned:g} points against configured capacity of {capacity:g}.", [str(iteration.get("iterationId"))]))
    return risks


def _health(items, remaining, risks, forecast, finish, today) -> str:
    if not items: return "InsufficientData"
    if not remaining: return "Completed"
    if any(item["severity"] == "High" for item in risks) or forecast.get("status") == "AtRisk": return "AtRisk"
    if risks or (finish and today > finish): return "NeedsAttention"
    return "Healthy"


def _interventions(risks: list[dict[str, Any]]) -> list[str]:
    actions = {
        "TooMuchWorkInProgress": "Finish or unblock active work before starting additional items.",
        "LateScopeAddition": "Review late scope additions and confirm which items remain committed for this sprint.",
        "BlockedDependency": "Assign an owner to each dependency and agree the next unblock action.",
        "PullRequestReviewBottleneck": "Schedule focused review time for aging pull requests.",
        "HighRiskUntestedWork": "Add explicit test coverage for high-risk work before completion.",
        "RepeatedBuildFailures": "Stabilize the build before adding further implementation scope.",
        "LargeUnfinishedStory": "Reassess or split large unfinished stories while preserving business value.",
        "StaleTask": "Review stale tasks and update their blocker, status, or sprint commitment.",
        "CapacityMismatch": "Reduce committed scope or explicitly revise the team capacity assumption.",
    }
    return [actions[item["signal"]] for item in risks if item["signal"] in actions] or ["Continue monitoring flow and complete required reviews and tests."]


def _evidence(project_id, iteration, items, prs, builds, accuracy) -> list[dict[str, Any]]:
    return [
        {"source": "AzureDevOpsSync", "type": "Iteration", "id": str(iteration.get("iterationId")), "reason": "Sprint dates and identity."},
        {"source": "AzureDevOpsSync", "type": "WorkItems", "count": len(items), "reason": "Scope, state, estimates, dates, dependencies, and reopen signals."},
        {"source": "AzureDevOpsSync", "type": "PullRequests", "count": len(prs), "reason": "Review waiting-time flow signal."},
        {"source": "AzureDevOpsSync", "type": "Builds", "count": len(builds), "reason": "Build reliability signal."},
        {"source": "EstimationIntelligence", "type": "Calibration", "sampleCount": accuracy.get("sampleCount", 0), "reason": "Estimate accuracy and uncertainty."},
    ]


def _blocker_public(entry):
    item = entry["item"]
    return {"workItemId": str(item.get("workItemId")), "title": str(item.get("title") or ""), "reasons": entry["reasons"]}


def _risk(signal, severity, reason, evidence): return {"signal": signal, "severity": severity, "reason": reason, "evidence": evidence}
def _complete(item): return str(item.get("state") or "").lower() in COMPLETED_STATES
def _estimate(item): return next((value for value in (item.get("storyPoints"), item.get("effort"), item.get("originalEstimate")) if value is not None), None)
def _points(item): return float(_estimate(item) or 0)
def _number(value):
    try: return float(value) if value not in (None, "") else None
    except (TypeError, ValueError): return None
def _date(value):
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try: return date.fromisoformat(str(value)[:10])
        except ValueError: return None
def _datetime(value, default):
    if not value: return default
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except ValueError: return default
def _utc(value): return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
def _uncalibrated(project_id, team_id): return {"projectId": project_id, "teamId": team_id, "calibrationScope": "Unavailable", "sampleCount": 0, "accuracy": None, "bias": "Insufficient history"}
def _report_id(project_id, iteration_id, items, now):
    revisions = ":".join(sorted(f"{item.get('workItemId')}:{item.get('revision')}" for item in items))
    return f"sprint-report-{hashlib.sha256(f'{project_id}:{iteration_id}:{revisions}:{now.date()}'.encode()).hexdigest()[:16]}"


def _sprint_added_at(history: Any, identities: set[str]) -> str:
    revisions = history.get("revisions") if isinstance(history, dict) else []
    matches = [
        item for item in revisions or []
        if isinstance(item, dict) and str(item.get("iterationPath") or "").strip().lower() in identities
    ]
    matches.sort(key=lambda item: str(item.get("changedAt") or item.get("createdAt") or ""))
    return str(matches[0].get("changedAt") or matches[0].get("createdAt") or "") if matches else ""
