"""Azure DevOps PR intelligence grounded in synchronized and approved HEI artifacts."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from backend.platform_sdk import as_azure_devops_sdk
from uuid import uuid4

from .pr_comment_builder import build_pr_comment
from .pr_repository import PullRequestIntelligenceRepository
from .service import WorkItemNotFoundError


PR_STATUSES = {"NotAnalyzed", "Analyzing", "NeedsReview", "ChangesRequired", "ReadyForReview", "ValidationFailed", "QAIncomplete"}
COMMENT_PERMISSION_ALIASES = {"pullrequests.contribute", "vso.code_write", "contribute to pull requests", "project administrators", "contributors"}


class PullRequestIntelligenceService:
    def __init__(self, *, azure_devops: Any, repository: PullRequestIntelligenceRepository, context_stores: dict[str, Any] | None = None, platform: Any | None = None) -> None:
        self.ado_sdk, self.repository, self.context_stores, self.platform = as_azure_devops_sdk(azure_devops), repository, context_stores or {}, platform

    def analyze(self, pull_request_id: str, request: dict[str, Any] | None = None, *, correlation_id: str = "") -> dict[str, Any]:
        request = request or {}; correlation_id = correlation_id or f"corr-{uuid4().hex[:16]}"
        self._event("PullRequestAnalysisRequested", request, pull_request_id, correlation_id)
        pr, project_id = self._resolve_pr(pull_request_id, request, correlation_id)
        linked = self._linked_work_items(pr, project_id, request)
        package = self._context("executionPackage", "executionPackages", request, linked, pr)
        runtime = self._context("runtimeSession", "runtimeSessions", request, linked, pr, package)
        diff = self._context("engineeringDiff", "engineeringDiffs", request, linked, pr, package, runtime)
        validation = self._context("validationResult", "validationResults", request, linked, pr, package, runtime, diff)
        qa = self._context("qaResult", "qaResults", request, linked, pr, package, runtime, diff)
        memory = self._contexts("memoryCandidates", "memoryCandidates", request, linked, pr, package, runtime, diff)
        candidate = self._context("prCandidate", "prCandidates", request, linked, pr, package, runtime, diff)
        plan = request.get("executionPlan") if isinstance(request.get("executionPlan"), dict) else {}
        changed_files = _changed_files(request, pr, diff, candidate)
        criteria = _acceptance(package, linked)
        acceptance = _acceptance_coverage(criteria, validation, qa)
        boundary = _boundary(package)
        unrelated = _unrelated_files(changed_files, package)
        blocked = _blocked_changes(changed_files, boundary)
        missing_tests = _missing_tests(qa, validation, criteria, changed_files)
        stale = _stale_snapshot(request, pr, package, diff)
        documentation_only = bool(changed_files) and all(_is_documentation(item.get("path", "")) for item in changed_files)
        architecture = _findings(diff, "architectureChanges")
        security = _security_findings(diff, validation, changed_files)
        breaking = _findings(diff, "breakingChanges")
        drift = _planned_drift(changed_files, package, unrelated, blocked)
        status = _status(linked, package, validation, qa, acceptance, blocked, unrelated, missing_tests, stale, documentation_only)
        warnings = _warnings(linked, package, stale, unrelated, missing_tests, validation, qa)
        recommendations = _recommendations(status, acceptance, blocked, unrelated, missing_tests, stale)
        report = {
            "reportId": _stable_id(project_id, pull_request_id, pr, package, diff), "reportVersion": "6.6",
            "pullRequestId": str(pull_request_id), "projectId": project_id, "repositoryId": str(pr.get("repositoryId") or request.get("repositoryId") or ""),
            "status": status, "changeSummary": _change_summary(pr, changed_files, diff),
            "implementationIntent": _implementation_intent(package, plan, candidate, pr),
            "pullRequestContext": {"title": pr.get("title"), "status": pr.get("status"), "sourceBranch": pr.get("sourceBranch"), "targetBranch": pr.get("targetBranch"), "sourceRevision": _pr_revision(pr), "commits": pr.get("commits") or [], "changedFiles": changed_files},
            "linkedWorkItems": linked, "linkedAcceptanceCriteria": criteria, "acceptanceCoverage": acceptance,
            "missingCriteria": [item for item in acceptance["criteria"] if item["status"] in {"Missing", "NotVerifiable"}],
            "plannedVsActualDrift": drift, "unrelatedChanges": unrelated, "blockedModuleChanges": blocked,
            "architectureFindings": architecture, "securityPermissionFindings": security,
            "missingTests": missing_tests, "regressionScope": _regression_scope(diff, changed_files, package),
            "risk": _risk(status, diff, blocked, unrelated, missing_tests, breaking), "breakingChanges": breaking,
            "reviewerRecommendations": recommendations, "blockingFindings": [*blocked, *[item["acceptanceText"] for item in acceptance["criteria"] if item["status"] == "Missing"]],
            "warnings": warnings, "documentationOnly": documentation_only,
            "context": {
                "executionPackage": _identity(package, "packageId"), "executionPlan": _identity(plan, "planId"),
                "runtimeSession": _identity(runtime, "sessionId"), "engineeringDiff": _identity(diff, "diffId"),
                "validationResult": _identity(validation, "reportId", "validationId"), "qaResult": _identity(qa, "reportId", "artifactId"),
                "memoryCandidates": [_identity(item, "candidateId") for item in memory], "prCandidate": _identity(candidate, "candidateId"),
                "repositorySnapshotBefore": request.get("repositorySnapshotBefore") or pr.get("repositorySnapshotBefore") or (diff.get("snapshotBefore") or {}).get("snapshotId"),
                "repositorySnapshotAfter": request.get("repositorySnapshotAfter") or pr.get("repositorySnapshotAfter") or (diff.get("snapshotAfter") or {}).get("snapshotId"),
            },
            "diagnostics": {"correlationId": correlation_id, "readOnlyAnalysis": True, "automaticCommentsPosted": 0, "pullRequestsApproved": 0, "pullRequestsMerged": 0, "contextSourcesResolved": sum(bool(value) for value in (package, plan, runtime, diff, validation, qa, memory, candidate)), "staleSnapshot": stale},
            "generatedAt": _now(),
        }
        report["commentPreviewAvailable"] = True
        saved = self.repository.save_report(report)
        self._event("PullRequestAnalysisCompleted", saved, pull_request_id, correlation_id)
        return saved

    def get(self, pull_request_id: str, project_id: str = "") -> dict[str, Any]:
        value = self.repository.get_report(pull_request_id, project_id)
        if not value: raise WorkItemNotFoundError(f"PR intelligence report for {pull_request_id}")
        return value

    def preview_comment(self, pull_request_id: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = request or {}; report = self.get(pull_request_id, str(request.get("projectId") or ""))
        preview = {
            "commentPreviewId": f"pr-comment-{uuid4().hex[:14]}", "reportId": report["reportId"],
            "pullRequestId": str(pull_request_id), "projectId": report["projectId"], "repositoryId": report["repositoryId"],
            "content": build_pr_comment(report), "approvalStatus": "PendingApproval", "posted": False,
            "sourceRevision": str((report.get("pullRequestContext") or {}).get("sourceRevision") or ""),
            "createdAt": _now(), "approvedBy": "", "postedAt": "",
        }
        saved = self.repository.save_comment(preview)
        self._event("PullRequestCommentApprovalRequired", saved, pull_request_id, str((report.get("diagnostics") or {}).get("correlationId") or ""))
        return saved

    def approve_comment_preview(self, preview_id: str, actor: str, reason: str = "") -> dict[str, Any]:
        return self._review_comment_preview(preview_id, actor, "Approved", reason)

    def reject_comment_preview(self, preview_id: str, actor: str, reason: str = "") -> dict[str, Any]:
        return self._review_comment_preview(preview_id, actor, "Rejected", reason)

    def _review_comment_preview(self, preview_id: str, actor: str, status: str, reason: str) -> dict[str, Any]:
        if not actor.strip():
            raise PermissionError("An authenticated reviewer is required for PR comment approval.")
        preview = self.repository.get_comment(preview_id)
        if not preview:
            raise WorkItemNotFoundError(f"PR comment preview {preview_id}")
        if preview.get("posted"):
            raise ValueError("Posted PR comments cannot be reviewed again.")
        if preview.get("approvalStatus") not in {"PendingApproval", "Pending"}:
            raise ValueError(f"PR comment preview is already {preview.get('approvalStatus')}.")
        timestamp = _now()
        preview.update({
            "approvalStatus": status, "reviewedBy": actor, "reviewedAt": timestamp,
            "approvalReason": reason,
            "approvedBy": actor if status == "Approved" else "",
            "approvedAt": timestamp if status == "Approved" else "",
            "rejectedBy": actor if status == "Rejected" else "",
            "rejectedAt": timestamp if status == "Rejected" else "",
        })
        saved = self.repository.save_comment(preview)
        if self.platform and getattr(self.platform, "audit", None):
            self.platform.audit.record({
                "action": f"PullRequestComment{status}", "actor": actor, "source": "ApprovalCenter",
                "targetType": "PullRequestComment", "targetId": preview_id, "before": {"approvalStatus": "PendingApproval"},
                "after": {"approvalStatus": status}, "reason": reason, "correlationId": f"corr-{uuid4().hex[:16]}",
            })
        return saved

    def post_approved_comment(self, pull_request_id: str, request: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        preview_id = str(request.get("commentPreviewId") or "")
        preview = self.repository.get_comment(preview_id)
        if not preview or preview["pullRequestId"] != str(pull_request_id): raise WorkItemNotFoundError(f"PR comment preview {preview_id}")
        actor = str(request.get("approvedBy") or preview.get("approvedBy") or "").strip()
        explicitly_approved = request.get("approved") is True or preview.get("approvalStatus") == "Approved"
        if not explicitly_approved or not actor: raise PermissionError("Explicit comment approval and approvedBy are required.")
        idempotency_key = str(request.get("idempotencyKey") or "").strip()
        if not idempotency_key: raise ValueError("idempotencyKey is required.")
        receipt_key = f"comment:{preview_id}:{idempotency_key}"
        existing = self.repository.receipt(receipt_key)
        if existing: return {**existing, "idempotentReplay": True}
        connection_id = str(request.get("connectionId") or ""); project_id = str(request.get("projectId") or preview.get("projectId") or ""); repository_id = str(request.get("repositoryId") or preview.get("repositoryId") or "")
        connection = self.ado_sdk.public_connection(connection_id)
        permissions = {str(item).strip().lower() for item in connection.get("permissions") or []}
        if not permissions & COMMENT_PERMISSION_ALIASES: raise PermissionError("Azure DevOps pull-request contribute permission is required.")
        if not project_id or not repository_id: raise ValueError("projectId and repositoryId are required.")
        current = self.ado_sdk.find_cached("pullRequests", str(pull_request_id), project_id)
        current_revision = _pr_revision(current[1] if current else {})
        approved_revision = str(preview.get("sourceRevision") or "")
        if not approved_revision:
            raise ValueError("PR source revision is required before posting an approved comment.")
        if current_revision and current_revision != approved_revision:
            raise ValueError("Pull request changed after comment approval. Reanalyze and approve a new comment preview.")
        correlation_id = correlation_id or f"corr-{uuid4().hex[:16]}"
        if not self.platform or not getattr(self.platform, "audit", None): raise ValueError("Audit service is required before posting a PR comment.")
        self.platform.audit.record({"action": "PullRequestCommentAuthorized", "actor": actor, "source": "API", "targetType": "AzureDevOpsPullRequest", "targetId": str(pull_request_id), "before": None, "after": {"commentPreviewId": preview_id}, "reason": str(request.get("reason") or "Approved HEI PR intelligence comment."), "correlationId": correlation_id})
        response = self.ado_sdk.post_pull_request_comment(connection_id, project_id, repository_id, int(pull_request_id), preview["content"], correlation_id=correlation_id)
        preview.update({"approvalStatus": "Approved", "approvedBy": actor, "posted": True, "postedAt": _now(), "externalThreadId": response.get("id") or response.get("threadId")})
        self.repository.save_comment(preview)
        result = {**preview, "idempotentReplay": False}
        self.repository.save_receipt(receipt_key, result)
        self._event("PullRequestCommentPosted", result, pull_request_id, correlation_id)
        return result

    def handle(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("eventType") or "")
        if event_type not in {"PullRequestCreated", "PullRequestUpdated", "PullRequestMerged", "AzureDevOpsPullRequestSynchronized"}: return
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        pr_id = str(payload.get("pullRequestId") or event.get("pullRequestId") or "")
        if not pr_id: return
        event_id = str(event.get("eventId") or hashlib.sha256(str(event).encode()).hexdigest())
        if self.repository.receipt(f"event:{event_id}"): return
        self.repository.save_receipt(f"event:{event_id}", {"eventId": event_id, "pullRequestId": pr_id, "receivedAt": _now()})
        try: self.analyze(pr_id, {"projectId": event.get("projectId") or payload.get("projectId") or ""}, correlation_id=str(event.get("correlationId") or ""))
        except (LookupError, ValueError): pass

    def _resolve_pr(self, pr_id: str, request: dict[str, Any], correlation_id: str) -> tuple[dict[str, Any], str]:
        project_id = str(request.get("projectId") or "")
        supplied = request.get("pullRequest") if isinstance(request.get("pullRequest"), dict) else None
        if supplied: return {**supplied, "pullRequestId": str(supplied.get("pullRequestId") or supplied.get("id") or pr_id)}, project_id or str(supplied.get("projectId") or "manual")
        cached = self.ado_sdk.find_cached("pullRequests", str(pr_id), project_id)
        if cached:
            pr = dict(cached[1]); project_id = cached[0]
        else: pr = {}
        connection_id = str(request.get("connectionId") or ""); repository_id = str(request.get("repositoryId") or pr.get("repositoryId") or "")
        if connection_id and project_id and repository_id:
            pr = self.ado_sdk.pull_request_context(connection_id, project_id, repository_id, int(pr_id), correlation_id=correlation_id)
            self.ado_sdk.cache_upsert(project_id, "pullRequests", str(pr_id), pr)
        if not pr: raise WorkItemNotFoundError(f"Pull request {pr_id}")
        return pr, project_id

    def _linked_work_items(self, pr: dict[str, Any], project_id: str, request: dict[str, Any]) -> list[dict[str, Any]]:
        supplied = request.get("linkedWorkItems") if isinstance(request.get("linkedWorkItems"), list) else []
        if supplied: return [dict(item) for item in supplied if isinstance(item, dict)]
        ids = pr.get("linkedWorkItemIds") or []
        result = []
        for value in ids:
            cached = self.ado_sdk.find_cached("workItems", str(value), project_id)
            result.append(dict(cached[1]) if cached else {"workItemId": str(value), "unresolved": True})
        return result

    def _context(self, request_key: str, store_key: str, request: dict[str, Any], *lineage: Any) -> dict[str, Any]:
        value = request.get(request_key)
        if isinstance(value, dict): return value
        values = self._read_store(store_key)
        explicit_id = str(request.get(f"{request_key}Id") or "")
        if explicit_id and isinstance(values.get(explicit_id), dict): return dict(values[explicit_id])
        return next((dict(item) for item in values.values() if isinstance(item, dict) and _lineage_match(item, lineage)), {})

    def _contexts(self, request_key: str, store_key: str, request: dict[str, Any], *lineage: Any) -> list[dict[str, Any]]:
        supplied = request.get(request_key)
        if isinstance(supplied, list): return [dict(item) for item in supplied if isinstance(item, dict)]
        return [dict(item) for item in self._read_store(store_key).values() if isinstance(item, dict) and _lineage_match(item, lineage)]

    def _read_store(self, name: str) -> dict[str, Any]:
        store = self.context_stores.get(name)
        return store.read() if store else {}

    def _event(self, event_type: str, payload: dict[str, Any], pr_id: str, correlation_id: str) -> None:
        if self.platform: self.platform.events.publish({"eventType": event_type, "source": "AzureDevOps", "projectId": payload.get("projectId"), "repositoryId": payload.get("repositoryId"), "correlationId": correlation_id, "payload": {"pullRequestId": str(pr_id), **payload}})


def _lineage_match(item: dict[str, Any], lineage: tuple[Any, ...]) -> bool:
    needles = {str(value) for source in lineage for value in _identifiers(source) if value}
    return bool(needles & set(_identifiers(item)))


def _pr_revision(value: dict[str, Any]) -> str:
    commit = value.get("lastMergeSourceCommit") or value.get("sourceCommitId") or value.get("lastMergeSourceCommitId") or ""
    if isinstance(commit, dict):
        commit = commit.get("commitId") or commit.get("id") or ""
    return str(value.get("revision") or commit or "")


def _identifiers(value: Any) -> list[str]:
    if isinstance(value, list): return [item for entry in value for item in _identifiers(entry)]
    if not isinstance(value, dict): return []
    keys = {"id", "workItemId", "storyId", "taskId", "packageId", "sourcePackageId", "sessionId", "diffId", "engineeringDiffId", "reportId", "candidateId", "artifactId", "pullRequestId"}
    result = [str(entry) for key, entry in value.items() if key in keys and entry not in (None, "")]
    for key in ("lineage", "sourceLineage", "metadata", "runtimeContext", "sourceArtifact", "planningContext"):
        result.extend(_identifiers(value.get(key)))
    return result


def _changed_files(request: dict[str, Any], pr: dict[str, Any], diff: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    values = request.get("changedFiles") or pr.get("changedFiles") or candidate.get("filesChanged") or []
    result = [_file(item) for item in values if _file(item).get("path")]
    if not result:
        for field in ("apiChanges", "moduleChanges", "serviceChanges", "testChanges", "securityChanges", "configurationChanges", "databaseChanges", "documentationChanges", "architectureChanges"):
            changes = diff.get(field) if isinstance(diff.get(field), dict) else {}
            for bucket in ("added", "modified", "removed", "moved"):
                result.extend(_file(item) for item in changes.get(bucket) or [] if _file(item).get("path"))
    unique = {item["path"]: item for item in result}
    return list(unique.values())


def _file(value: Any) -> dict[str, Any]:
    if isinstance(value, str): return {"path": value, "changeType": "Modified"}
    if not isinstance(value, dict): return {}
    before = value.get("before") if isinstance(value.get("before"), dict) else {}; after = value.get("after") if isinstance(value.get("after"), dict) else {}; item = value.get("item") if isinstance(value.get("item"), dict) else {}
    return {"path": str(value.get("path") or after.get("path") or before.get("path") or item.get("path") or ""), "changeType": str(value.get("changeType") or "Modified"), "diff": str(value.get("diff") or value.get("patch") or "")}


def _acceptance(package: dict[str, Any], linked: list[dict[str, Any]]) -> list[dict[str, str]]:
    values = package.get("acceptanceMapping") if isinstance(package.get("acceptanceMapping"), list) else (package.get("planningContext") or {}).get("acceptanceCriteria") or []
    if not values and linked: values = linked[0].get("acceptanceCriteria") or []
    if isinstance(values, str): values = [line for line in values.splitlines() if line.strip()]
    result = []
    for index, item in enumerate(values):
        text = str(item.get("acceptanceText") or item.get("text") or item.get("title") or "") if isinstance(item, dict) else str(item)
        if text: result.append({"acceptanceCriteriaId": str(item.get("acceptanceCriteriaId") or item.get("id") or f"AC-{index + 1}") if isinstance(item, dict) else f"AC-{index + 1}", "acceptanceText": text})
    return result


def _acceptance_coverage(criteria: list[dict[str, str]], validation: dict[str, Any], qa: dict[str, Any]) -> dict[str, Any]:
    results = validation.get("acceptanceResults") if isinstance(validation.get("acceptanceResults"), list) else []
    qa_coverage = qa.get("acceptanceCoverage") if isinstance(qa.get("acceptanceCoverage"), dict) else {}
    mapped = []
    for index, criterion in enumerate(criteria):
        match = next((item for item in results if str(item.get("acceptanceCriteriaId") or item.get("id")) == criterion["acceptanceCriteriaId"]), results[index] if index < len(results) else {})
        raw = str(match.get("status") or "NotVerifiable").replace(" ", "")
        status = "Covered" if raw.lower() in {"implemented", "covered", "passed", "verified"} else "PartiallyCovered" if "partial" in raw.lower() else "Missing" if raw.lower() in {"missing", "notcovered"} else "NotVerifiable"
        mapped.append({**criterion, "status": status, "evidence": match.get("evidence") or []})
    score = validation.get("acceptanceCoverageScore") or qa_coverage.get("coverageScore")
    if score is None: score = round((sum(item["status"] == "Covered" for item in mapped) + .5 * sum(item["status"] == "PartiallyCovered" for item in mapped)) / len(mapped) * 100) if mapped else 0
    return {"score": int(score), "criteria": mapped, "covered": sum(item["status"] == "Covered" for item in mapped), "total": len(mapped)}


def _boundary(package: dict[str, Any]) -> dict[str, list[str]]:
    value = package.get("implementationBoundary") if isinstance(package.get("implementationBoundary"), dict) else {}
    return {"allowedModules": list(value.get("allowedModules") or value.get("allowed_modules") or []), "blockedModules": list(value.get("blockedModules") or value.get("blocked_modules") or []), "outOfScope": list(value.get("outOfScope") or value.get("out_of_scope") or [])}


def _unrelated_files(files: list[dict[str, Any]], package: dict[str, Any]) -> list[str]:
    context = package.get("repositoryContext") if isinstance(package.get("repositoryContext"), dict) else {}
    ranked = context.get("relevantFiles") or package.get("relevantFiles") or []
    allowed = {str(item.get("path") if isinstance(item, dict) else item).lower() for item in ranked}
    if not allowed: return []
    return [item["path"] for item in files if item["path"].lower() not in allowed and not _is_test(item["path"])]


def _blocked_changes(files: list[dict[str, Any]], boundary: dict[str, list[str]]) -> list[str]:
    blocked = [str(item).lower() for item in [*boundary["blockedModules"], *boundary["outOfScope"]]]
    return [f"Blocked scope changed: {item['path']}" for item in files if any(term.replace(" ", "") in item["path"].lower().replace("-", "").replace("_", "") for term in blocked if term)]


def _missing_tests(qa: dict[str, Any], validation: dict[str, Any], criteria: list[dict[str, str]], files: list[dict[str, Any]]) -> list[str]:
    values = qa.get("missingTests") or (qa.get("testGapAnalysis") or {}).get("missingTests") or []
    result = [str(item.get("title") or item.get("description") or item) if isinstance(item, dict) else str(item) for item in values]
    test_score = validation.get("testCoverageScore")
    documentation_only = bool(files) and all(_is_documentation(item["path"]) for item in files)
    if criteria and not documentation_only and not any(_is_test(item["path"]) for item in files) and (test_score is None or int(test_score) < 80): result.append("No changed test file verifies the linked acceptance criteria.")
    return list(dict.fromkeys(result))


def _stale_snapshot(request: dict[str, Any], pr: dict[str, Any], package: dict[str, Any], diff: dict[str, Any]) -> bool:
    package_version = str((package.get("metadata") or {}).get("repositorySnapshotVersion") or package.get("repositorySnapshotVersion") or "")
    current = str(request.get("repositorySnapshotAfter") or pr.get("repositorySnapshotAfter") or diff.get("repositorySnapshotVersion") or "")
    return bool(package_version and current and package_version != current)


def _status(linked, package, validation, qa, acceptance, blocked, unrelated, missing_tests, stale, docs_only) -> str:
    if str(validation.get("status") or "").lower() in {"failed", "blocked"}: return "ValidationFailed"
    if blocked or any(item["status"] == "Missing" for item in acceptance["criteria"]): return "ChangesRequired"
    qa_status = str(qa.get("status") or qa.get("readinessStatus") or (qa.get("qaReadiness") or {}).get("status") or "").lower()
    if missing_tests or qa_status in {"blocked", "needs review", "needsreview", "incomplete"}: return "QAIncomplete"
    if not linked or not package or stale or unrelated: return "NeedsReview"
    if docs_only and not validation and not qa: return "NeedsReview"
    return "ReadyForReview"


def _warnings(linked, package, stale, unrelated, missing_tests, validation, qa) -> list[str]:
    values = []
    if not linked: values.append("No linked Azure DevOps work item is available.")
    if not package: values.append("No Execution Package is linked to this pull request.")
    if stale: values.append("The Execution Package repository snapshot is stale relative to the PR context.")
    if unrelated: values.append(f"{len(unrelated)} changed file(s) are outside the ranked package context.")
    if missing_tests: values.append(f"{len(missing_tests)} required test item(s) are missing.")
    if not validation: values.append("Implementation Validation is unavailable.")
    if not qa: values.append("QA Intelligence result is unavailable.")
    return values


def _recommendations(status, acceptance, blocked, unrelated, tests, stale) -> list[str]:
    result = []
    if any(item["status"] != "Covered" for item in acceptance["criteria"]): result.append("Verify every linked acceptance criterion with implementation and test evidence.")
    if blocked: result.append("Remove blocked-scope changes or obtain a new approved implementation boundary.")
    if unrelated: result.append("Review unrelated changed files and split unrelated work from this pull request.")
    if tests: result.append("Add the missing tests and rerun Implementation Validation and QA Intelligence.")
    if stale: result.append("Refresh repository context and rebuild the Execution Package before relying on readiness.")
    if not result and status == "ReadyForReview": result.append("Proceed with human code review and required external branch policies.")
    return result


def _findings(diff: dict[str, Any], field: str) -> list[str]:
    value = diff.get(field) if isinstance(diff.get(field), dict) else {}
    result = []
    for bucket in ("added", "modified", "removed", "moved"):
        for item in value.get(bucket) or []:
            if isinstance(item, dict): result.append(str(item.get("reason") or item.get("name") or (item.get("after") or {}).get("name") or field))
    return result


def _security_findings(diff, validation, files) -> list[str]:
    values = _findings(diff, "securityChanges")
    for item in validation.get("violations") or []:
        text = str(item.get("message") or item.get("rule") or item) if isinstance(item, dict) else str(item)
        if any(term in text.lower() for term in ("security", "permission", "authorization", "authentication")): values.append(text)
    if any(any(term in item["path"].lower() for term in ("auth", "permission", "security")) for item in files) and not values: values.append("Security-sensitive files changed; permission and authorization review is required.")
    return list(dict.fromkeys(values))


def _planned_drift(files, package, unrelated, blocked) -> dict[str, Any]:
    return {"status": "DriftDetected" if unrelated or blocked else "Aligned" if package else "NotVerifiable", "changedFileCount": len(files), "unrelatedFileCount": len(unrelated), "blockedChangeCount": len(blocked)}


def _regression_scope(diff, files, package) -> list[str]:
    modules = _findings(diff, "moduleChanges")
    if not modules: modules = list((_boundary(package)).get("allowedModules") or [])
    return list(dict.fromkeys([*modules, *[item["path"] for item in files if _is_test(item["path"])]]))


def _risk(status, diff, blocked, unrelated, tests, breaking) -> dict[str, Any]:
    level = "Critical" if blocked or breaking else "High" if status in {"ChangesRequired", "ValidationFailed"} else "Medium" if unrelated or tests or status in {"NeedsReview", "QAIncomplete"} else str((diff.get("impact") or {}).get("level") or "Low")
    return {"level": level, "reasons": [*blocked, *unrelated, *tests, *breaking]}


def _change_summary(pr, files, diff) -> str:
    total = (diff.get("summary") or {}).get("totalChanges") or len(files)
    return f"{pr.get('title') or 'Pull request'} contains {total} engineering change(s) across {len(files)} changed file(s)."


def _implementation_intent(package, plan, candidate, pr) -> str:
    return str((package.get("implementationGuidance") or {}).get("implementationObjective") or (package.get("businessContext") or {}).get("taskObjective") or plan.get("objective") or (candidate.get("summary") or {}).get("title") or pr.get("title") or "Implementation intent requires review.")


def _identity(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {"id": next((str(value.get(key)) for key in keys if value.get(key)), ""), "available": bool(value)}


def _stable_id(project_id, pr_id, pr, package, diff) -> str:
    value = f"{project_id}:{pr_id}:{pr.get('sourceCommitId')}:{_identity(package, 'packageId')['id']}:{_identity(diff, 'diffId')['id']}"
    return f"ado-pr-report-{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def _is_test(path: str) -> bool: return any(term in path.lower() for term in ("test", "spec", "__tests__"))
def _is_documentation(path: str) -> bool: return path.lower().endswith((".md", ".txt", ".rst")) or "/docs/" in path.lower() or path.lower().startswith("docs/")
def _now() -> str: return datetime.now(timezone.utc).isoformat()
