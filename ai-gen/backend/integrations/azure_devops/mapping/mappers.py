"""Maps provider DTOs into stable HEI integration models."""

from __future__ import annotations

from typing import Any

from ..domain import (
    ExternalBuild, ExternalIteration, ExternalProject, ExternalPullRequest, ExternalRepository,
    ExternalTeam, ExternalWorkItem, ExternalWorkItemLink,
)


def map_project(value: dict[str, Any]) -> ExternalProject:
    return ExternalProject(str(value.get("id") or ""), str(value.get("name") or ""), str(value.get("description") or ""), str(value.get("state") or ""), str(value.get("visibility") or ""), str(value.get("url") or ""))


def map_team(value: dict[str, Any]) -> ExternalTeam:
    project = value.get("project") if isinstance(value.get("project"), dict) else {}
    return ExternalTeam(str(value.get("id") or ""), str(value.get("name") or ""), str(value.get("projectId") or project.get("id") or ""), str(value.get("description") or ""), str(value.get("url") or ""))


def map_iteration(value: dict[str, Any]) -> ExternalIteration:
    attributes = value.get("attributes") if isinstance(value.get("attributes"), dict) else {}
    return ExternalIteration(str(value.get("id") or value.get("identifier") or ""), str(value.get("name") or ""), str(value.get("path") or ""), str(attributes.get("startDate") or ""), str(attributes.get("finishDate") or ""), str(attributes.get("timeFrame") or ""))


def map_work_item_link(value: dict[str, Any]) -> ExternalWorkItemLink:
    target_url = str(value.get("url") or "")
    return ExternalWorkItemLink(str(value.get("rel") or "related"), target_url.rstrip("/").split("/")[-1], target_url, dict(value.get("attributes") or {}))


def map_work_item(value: dict[str, Any]) -> ExternalWorkItem:
    fields = value.get("fields") if isinstance(value.get("fields"), dict) else {}
    assigned = fields.get("System.AssignedTo")
    assigned_name = str(assigned.get("displayName") or assigned.get("uniqueName") or "") if isinstance(assigned, dict) else str(assigned or "")
    return ExternalWorkItem(
        int(value.get("id") or 0), str(fields.get("System.WorkItemType") or ""), str(fields.get("System.Title") or ""),
        str(fields.get("System.State") or ""), str(fields.get("System.Description") or ""),
        str(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria") or ""), str(fields.get("System.TeamProject") or ""),
        assigned_name, str(fields.get("System.AreaPath") or ""), str(fields.get("System.IterationPath") or ""),
        int(value.get("rev") or 0), [map_work_item_link(item) for item in value.get("relations", []) if isinstance(item, dict)],
        str(fields.get("System.ChangedDate") or ""), str(value.get("url") or ""),
        _number(fields.get("Microsoft.VSTS.Scheduling.StoryPoints")),
        _number(fields.get("Microsoft.VSTS.Scheduling.Effort")),
        _number(fields.get("Microsoft.VSTS.Scheduling.OriginalEstimate")),
        _number(fields.get("Microsoft.VSTS.Scheduling.RemainingWork")),
        _number(fields.get("Microsoft.VSTS.Scheduling.CompletedWork")),
        str(fields.get("System.CreatedDate") or ""), str(fields.get("Microsoft.VSTS.Common.ActivatedDate") or ""),
        str(fields.get("Microsoft.VSTS.Common.ClosedDate") or ""), str(fields.get("Microsoft.VSTS.Common.StateChangeDate") or ""),
        _tags(fields.get("System.Tags")), str(value.get("teamId") or fields.get("Custom.TeamId") or ""),
        int(value.get("reopenCount") or fields.get("Custom.ReopenCount") or 0),
        int(value.get("prIterations") or fields.get("Custom.PRIterations") or 0),
        int(value.get("escapedDefects") or fields.get("Custom.EscapedDefects") or 0),
        _number(value.get("actualCycleTimeDays") or fields.get("Custom.ActualCycleTimeDays")),
        _number(value.get("actualActiveTimeDays") or fields.get("Custom.ActualActiveTimeDays")),
        [_comment(item) for item in value.get("comments") or [] if isinstance(item, dict)],
        [_attachment(item) for item in value.get("relations") or [] if isinstance(item, dict) and str(item.get("rel") or "").lower() == "attachedfile"],
    )


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _comment(value: dict[str, Any]) -> dict[str, Any]:
    author = value.get("createdBy") if isinstance(value.get("createdBy"), dict) else {}
    return {
        "commentId": str(value.get("id") or ""),
        "text": str(value.get("text") or ""),
        "createdBy": str(author.get("displayName") or author.get("uniqueName") or ""),
        "createdAt": str(value.get("createdDate") or ""),
        "modifiedAt": str(value.get("modifiedDate") or ""),
    }


def _attachment(value: dict[str, Any]) -> dict[str, Any]:
    attributes = value.get("attributes") if isinstance(value.get("attributes"), dict) else {}
    return {
        "name": str(attributes.get("name") or "Attachment"),
        "url": str(value.get("url") or ""),
        "comment": str(attributes.get("comment") or ""),
        "authorizedDate": str(attributes.get("authorizedDate") or ""),
    }


def map_repository(value: dict[str, Any]) -> ExternalRepository:
    project = value.get("project") if isinstance(value.get("project"), dict) else {}
    return ExternalRepository(str(value.get("id") or ""), str(value.get("name") or ""), str(project.get("id") or ""), str(project.get("name") or ""), str(value.get("defaultBranch") or ""), str(value.get("remoteUrl") or ""), str(value.get("webUrl") or ""), int(value.get("size") or 0))


def map_pull_request(value: dict[str, Any]) -> ExternalPullRequest:
    repository = value.get("repository") if isinstance(value.get("repository"), dict) else {}
    created_by = value.get("createdBy") if isinstance(value.get("createdBy"), dict) else {}
    source_commit = value.get("lastMergeSourceCommit") if isinstance(value.get("lastMergeSourceCommit"), dict) else {}
    target_commit = value.get("lastMergeTargetCommit") if isinstance(value.get("lastMergeTargetCommit"), dict) else {}
    linked = value.get("linkedWorkItemIds") or value.get("workItemIds") or []
    return ExternalPullRequest(
        int(value.get("pullRequestId") or value.get("id") or 0), str(value.get("title") or ""), str(value.get("status") or ""),
        str(repository.get("id") or value.get("repositoryId") or ""), str(value.get("sourceRefName") or value.get("sourceBranch") or ""),
        str(value.get("targetRefName") or value.get("targetBranch") or ""), str(created_by.get("displayName") or created_by.get("uniqueName") or ""),
        str(value.get("creationDate") or ""), bool(value.get("isDraft", False)), str(value.get("mergeStatus") or ""), str(value.get("url") or ""),
        [str(item.get("id") if isinstance(item, dict) else item) for item in linked if str(item.get("id") if isinstance(item, dict) else item)],
        [dict(item) for item in value.get("commits") or [] if isinstance(item, dict)],
        [dict(item) for item in value.get("changedFiles") or value.get("changes") or [] if isinstance(item, dict)],
        str(value.get("sourceCommitId") or source_commit.get("commitId") or ""), str(value.get("targetCommitId") or target_commit.get("commitId") or ""),
        str(value.get("repositorySnapshotBefore") or ""), str(value.get("repositorySnapshotAfter") or ""),
    )


def map_build(value: dict[str, Any]) -> ExternalBuild:
    definition = value.get("definition") if isinstance(value.get("definition"), dict) else {}
    return ExternalBuild(int(value.get("id") or 0), str(value.get("buildNumber") or ""), str(value.get("status") or ""), str(value.get("result") or ""), str(definition.get("name") or ""), str(value.get("sourceBranch") or ""), str(value.get("sourceVersion") or ""), str(value.get("queueTime") or ""), str(value.get("startTime") or ""), str(value.get("finishTime") or ""), str(value.get("url") or ""))
