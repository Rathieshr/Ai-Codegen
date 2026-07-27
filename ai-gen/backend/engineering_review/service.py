"""Version-aware Engineering Review and approval workflow."""

from __future__ import annotations

import hashlib
import base64
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from backend.platform.shared import JsonMapStore

from .models import (
    CHANGE_REQUEST_TYPES,
    INLINE_TARGETS,
    REVIEW_SECTIONS,
    EngineeringReview,
    ReviewStageDefinition,
)


DEFAULT_APPROVAL_CHAIN = (
    ("product-owner", "Product Owner", "Product Owner"),
    ("engineering-lead", "Engineering Lead", "Engineering Lead"),
    ("architect", "Architect", "Architect"),
    ("qa-lead", "QA Lead", "QA Lead"),
    ("delivery-manager", "Delivery Manager", "Delivery Manager"),
)

TERMINAL_STATUSES = {"Approved", "Rejected", "Expired", "Superseded"}


class EngineeringReviewService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        proposal_provider: Callable[[str], dict[str, Any]],
        proposal_approver: Callable[[str, str, str], dict[str, Any]],
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.proposal_provider = proposal_provider
        self.proposal_approver = proposal_approver
        self.platform = platform

    def create(self, request: dict[str, Any]) -> dict[str, Any]:
        proposal_id = _required(request, "proposalId")
        proposal = self.proposal_provider(proposal_id)
        values = self.store.read()
        current = self._for_proposal(values, proposal_id)
        if current and int(current.get("proposalVersion") or 0) == int(proposal.get("version") or 0):
            return self._dashboard(current, proposal)
        if current and current.get("status") not in TERMINAL_STATUSES:
            current["status"] = "Superseded"
            current["updatedAt"] = _now()
            values[current["reviewId"]] = current

        owner = _text(request.get("owner") or request.get("actor")) or "HEI User"
        stages = _stages(request.get("approvalChain"))
        now = _now()
        review_id = "engineering-review-" + _digest([proposal_id, proposal.get("version")])
        review = EngineeringReview(
            reviewId=review_id,
            proposalId=proposal_id,
            proposalVersion=int(proposal.get("version") or 0),
            contextVersion=_text(proposal.get("contextVersion") or proposal.get("contextId")),
            knowledgeVersion=_text(proposal.get("knowledgeVersion")),
            recommendationVersion=_recommendation_version(proposal),
            status="PendingReview",
            owner=owner,
            currentStageId=stages[0]["stageId"] if stages else "",
            stages=stages,
            sections=[
                {"name": name, "status": "Pending", "commentCount": 0, "approvedBy": "", "approvedAt": ""}
                for name in REVIEW_SECTIONS
            ],
            affectedRepositories=_affected_repositories(proposal),
            affectedTeams=_affected_teams(proposal),
            expiresAt=_text(request.get("expiresAt")),
            createdAt=now,
            updatedAt=now,
        ).__dict__
        review["readiness"] = self._readiness(review, proposal)
        values[review_id] = review
        self.store.write(values)
        self._event("EngineeringReviewAssigned", review)
        self._notify_reviewers(review, "Engineering review assigned", "A Planning Proposal is ready for review.")
        self._audit(review, owner, "EngineeringReviewCreated", "Engineering review created.")
        return self._dashboard(review, proposal)

    def get(self, review_id: str) -> dict[str, Any]:
        review = self.store.read().get(review_id)
        if not isinstance(review, dict):
            raise LookupError("Engineering Review was not found.")
        proposal = self.proposal_provider(review["proposalId"])
        return self._dashboard(review, proposal)

    def for_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.proposal_provider(proposal_id)
        review = self._for_proposal(self.store.read(), proposal_id)
        if not review:
            raise LookupError("Engineering Review was not found for this Planning Proposal.")
        return self._dashboard(review, proposal)

    def list(
        self,
        *,
        status: str = "",
        reviewer: str = "",
        search: str = "",
    ) -> dict[str, Any]:
        records = list(self.store.read().values())
        query = search.casefold().strip()
        output = []
        for review in records:
            if not isinstance(review, dict):
                continue
            if status and _text(review.get("status")).casefold() != status.casefold():
                continue
            assigned = [
                _text(stage.get("assignedReviewer"))
                for stage in review.get("stages") or []
            ]
            if reviewer and reviewer not in assigned:
                continue
            if query and query not in " ".join((
                _text(review.get("reviewId")),
                _text(review.get("proposalId")),
                _text(review.get("owner")),
            )).casefold():
                continue
            try:
                output.append(self._dashboard(review, self.proposal_provider(review["proposalId"])))
            except LookupError:
                output.append(deepcopy(review))
        output.sort(key=lambda item: item.get("updatedAt", ""), reverse=True)
        return {"reviews": output, "count": len(output), "generatedAt": _now()}

    def assign(self, review_id: str, request: dict[str, Any]) -> dict[str, Any]:
        review, values = self._editable(review_id)
        stage = self._stage(review, _required(request, "stageId"))
        stage["assignedReviewer"] = _required(request, "reviewer")
        stage["assignedAt"] = _now()
        stage["assignedBy"] = _text(request.get("actor")) or "HEI User"
        review["updatedAt"] = _now()
        values[review_id] = review
        self.store.write(values)
        self._event("EngineeringReviewAssigned", review)
        self._notify(
            review,
            "Review assigned",
            f"You were assigned the {stage['name']} stage.",
            target_user=stage["assignedReviewer"],
        )
        self._audit(review, stage["assignedBy"], "EngineeringReviewAssigned", stage["name"])
        return self._dashboard(review, self.proposal_provider(review["proposalId"]))

    def comment(self, review_id: str, request: dict[str, Any]) -> dict[str, Any]:
        review, values = self._editable(review_id)
        target_type = _required(request, "targetType")
        if target_type not in INLINE_TARGETS and target_type not in REVIEW_SECTIONS:
            raise ValueError(f"Unsupported review comment target: {target_type}.")
        body = _required(request, "comment")
        comment = {
            "commentId": "review-comment-" + _digest([review_id, len(review["comments"]), body]),
            "section": _text(request.get("section")) or _section_for_target(target_type),
            "targetType": target_type,
            "targetId": _text(request.get("targetId")),
            "comment": body,
            "author": _required(request, "actor"),
            "status": "Open",
            "proposalVersion": review["proposalVersion"],
            "createdAt": _now(),
            "updatedAt": _now(),
        }
        review["comments"].append(comment)
        self._update_section_counts(review)
        review["status"] = "InReview"
        review["updatedAt"] = _now()
        values[review_id] = review
        self.store.write(values)
        self._event("EngineeringReviewCommented", review)
        self._audit(review, comment["author"], "EngineeringReviewCommented", body)
        return self._dashboard(review, self.proposal_provider(review["proposalId"]))

    def resolve_comment(self, review_id: str, comment_id: str, request: dict[str, Any]) -> dict[str, Any]:
        review, values = self._editable(review_id)
        comment = next((item for item in review["comments"] if item["commentId"] == comment_id), None)
        if not comment:
            raise LookupError("Review comment was not found.")
        comment["status"] = "Resolved"
        comment["resolvedBy"] = _required(request, "actor")
        comment["resolution"] = _text(request.get("resolution"))
        comment["updatedAt"] = _now()
        self._update_section_counts(review)
        review["updatedAt"] = _now()
        values[review_id] = review
        self.store.write(values)
        return self._dashboard(review, self.proposal_provider(review["proposalId"]))

    def request_change(self, review_id: str, request: dict[str, Any]) -> dict[str, Any]:
        review, values = self._editable(review_id)
        change_type = _required(request, "changeType")
        if change_type not in CHANGE_REQUEST_TYPES:
            raise ValueError(f"Unsupported change request type: {change_type}.")
        item = {
            "changeRequestId": "review-change-" + _digest([
                review_id, len(review["changeRequests"]), change_type, request.get("description"),
            ]),
            "type": change_type,
            "description": _required(request, "description"),
            "targetId": _text(request.get("targetId")),
            "requestedBy": _required(request, "actor"),
            "status": "Open",
            "proposalVersion": review["proposalVersion"],
            "createdAt": _now(),
            "resolvedAt": "",
            "resolution": "",
        }
        review["changeRequests"].append(item)
        review["status"] = "ChangesRequested"
        review["updatedAt"] = _now()
        review["readiness"] = self._readiness(review, self.proposal_provider(review["proposalId"]))
        values[review_id] = review
        self.store.write(values)
        self._event("EngineeringReviewChangesRequested", review)
        self._notify_reviewers(review, "Changes requested", item["description"])
        self._audit(review, item["requestedBy"], "EngineeringReviewChangesRequested", item["description"])
        return self._dashboard(review, self.proposal_provider(review["proposalId"]))

    def resolve_change(self, review_id: str, change_id: str, request: dict[str, Any]) -> dict[str, Any]:
        review, values = self._editable(review_id)
        item = next((entry for entry in review["changeRequests"] if entry["changeRequestId"] == change_id), None)
        if not item:
            raise LookupError("Change request was not found.")
        item["status"] = "Resolved"
        item["resolvedBy"] = _required(request, "actor")
        item["resolution"] = _required(request, "resolution")
        item["resolvedAt"] = _now()
        review["status"] = "InReview"
        review["updatedAt"] = _now()
        review["readiness"] = self._readiness(review, self.proposal_provider(review["proposalId"]))
        values[review_id] = review
        self.store.write(values)
        return self._dashboard(review, self.proposal_provider(review["proposalId"]))

    def decide(self, review_id: str, request: dict[str, Any]) -> dict[str, Any]:
        review, values = self._editable(review_id)
        proposal = self.proposal_provider(review["proposalId"])
        self._assert_current_version(review, proposal)
        decision = _required(request, "decision")
        if decision not in {"Approve", "ApproveWithComments", "RequestChanges", "Reject", "SaveDraftReview"}:
            raise ValueError("Unsupported review decision.")
        actor = _required(request, "actor")
        comments = _text(request.get("comments"))
        if decision in {"ApproveWithComments", "RequestChanges", "Reject"} and not comments:
            raise ValueError(f"Comments are required for {decision}.")
        if decision == "SaveDraftReview":
            review["status"] = "Draft"
            review["updatedAt"] = _now()
            values[review_id] = review
            self.store.write(values)
            return self._dashboard(review, proposal)
        if decision == "RequestChanges":
            return self.request_change(review_id, {
                "changeType": _text(request.get("changeType")) or "Business Clarification",
                "description": comments,
                "targetId": request.get("targetId"),
                "actor": actor,
            })

        stage = self._current_stage(review)
        self._assert_reviewer(stage, actor, _text(request.get("role")))
        readiness = self._readiness(review, proposal, final=False)
        if decision.startswith("Approve") and not readiness["stageApprovalAllowed"]:
            raise ValueError("Engineering Review cannot continue: " + "; ".join(readiness["blockers"]))
        record = {
            "decisionId": "review-decision-" + _digest([review_id, len(review["decisions"]), actor, decision]),
            "stageId": stage["stageId"],
            "stage": stage["name"],
            "reviewer": actor,
            "role": _text(request.get("role")) or stage["role"],
            "decision": decision,
            "comments": comments,
            "proposalVersion": review["proposalVersion"],
            "contextVersion": review["contextVersion"],
            "knowledgeVersion": review["knowledgeVersion"],
            "timestamp": _now(),
        }
        review["decisions"].append(record)
        if decision == "Reject":
            stage["status"] = "Rejected"
            review["status"] = "Rejected"
            review["currentStageId"] = ""
            event = "EngineeringReviewRejected"
        else:
            stage["status"] = "Approved"
            stage["approvedBy"] = actor
            stage["approvedAt"] = record["timestamp"]
            self._approve_sections(review, stage, actor)
            next_stage = self._next_stage(review, stage)
            if next_stage:
                review["currentStageId"] = next_stage["stageId"]
                review["status"] = "InReview"
                event = "EngineeringReviewStageApproved"
                self._notify(
                    review,
                    "Engineering review ready",
                    f"The {next_stage['name']} stage is ready.",
                    target_user=_text(next_stage.get("assignedReviewer")),
                    target_role=next_stage["role"],
                )
            else:
                final_readiness = self._readiness(review, proposal, final=True)
                if not final_readiness["approvalAllowed"]:
                    stage["status"] = "Pending"
                    stage["approvedBy"] = ""
                    stage["approvedAt"] = ""
                    review["status"] = "NeedsReview"
                    review["readiness"] = final_readiness
                    values[review_id] = review
                    self.store.write(values)
                    raise ValueError("Final approval is blocked: " + "; ".join(final_readiness["blockers"]))
                approved = self.proposal_approver(review["proposalId"], actor, comments)
                review["status"] = "Approved"
                review["approvedBy"] = actor
                review["approvedAt"] = record["timestamp"]
                review["proposalVersion"] = int(approved.get("version") or review["proposalVersion"])
                review["currentStageId"] = ""
                event = "EngineeringReviewApproved"
        review["updatedAt"] = _now()
        review["readiness"] = self._readiness(review, self.proposal_provider(review["proposalId"]))
        values[review_id] = review
        self.store.write(values)
        self._event(event, review)
        self._notify_reviewers(review, event.replace("EngineeringReview", "Engineering review "), comments)
        self._audit(review, actor, event, comments)
        return self._dashboard(review, self.proposal_provider(review["proposalId"]))

    def invalidate(self, proposal_id: str, proposal_version: int, actor: str = "HEI") -> None:
        values = self.store.read()
        review = self._for_proposal(values, proposal_id)
        if not review or int(review.get("proposalVersion") or 0) == int(proposal_version):
            return
        review["status"] = "Superseded"
        review["invalidatedAt"] = _now()
        review["invalidatedBy"] = actor
        review["invalidationReason"] = f"Planning Proposal changed to version {proposal_version}."
        review["updatedAt"] = _now()
        values[review["reviewId"]] = review
        self.store.write(values)
        self._event("EngineeringReviewInvalidated", review)
        self._notify_reviewers(review, "Engineering review invalidated", review["invalidationReason"])

    def authorize_synchronization(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.proposal_provider(proposal_id)
        review = self._for_proposal(self.store.read(), proposal_id)
        reasons = []
        if not review:
            reasons.append("Engineering Review has not been created.")
        else:
            if review.get("status") != "Approved":
                reasons.append("Engineering Review is not approved.")
            if int(review.get("proposalVersion") or 0) != int(proposal.get("version") or 0):
                reasons.append("Engineering Review does not match the current proposal version.")
        if proposal.get("status") != "Approved":
            reasons.append("Planning Proposal is not approved.")
        return {
            "proposalId": proposal_id,
            "authorized": not reasons,
            "status": "Authorized" if not reasons else "Blocked",
            "reasons": reasons,
            "reviewId": _text((review or {}).get("reviewId")),
            "proposalVersion": proposal.get("version"),
            "checkedAt": _now(),
        }

    def report(
        self,
        review_id: str,
        report_type: str = "Review Report",
        output_format: str = "Markdown",
    ) -> dict[str, Any]:
        dashboard = self.get(review_id)
        allowed = {
            "Review Report", "Approval Report", "Planning Summary",
            "Architecture Summary", "Decision Log",
        }
        if report_type not in allowed:
            raise ValueError("Unsupported Engineering Review report type.")
        markdown = _markdown_report(dashboard, report_type)
        normalized_format = _text(output_format).casefold()
        if normalized_format not in {"markdown", "pdf"}:
            raise ValueError("Engineering Review reports support Markdown or PDF.")
        result = {
            "reportId": "review-report-" + _digest([review_id, report_type, dashboard["proposalVersion"]]),
            "reviewId": review_id,
            "reportType": report_type,
            "format": "PDF" if normalized_format == "pdf" else "Markdown",
            "generatedAt": _now(),
        }
        if normalized_format == "pdf":
            result["mediaType"] = "application/pdf"
            result["fileName"] = f"{report_type.casefold().replace(' ', '-')}-{review_id}.pdf"
            result["contentBase64"] = base64.b64encode(_simple_pdf(markdown)).decode("ascii")
        else:
            result["mediaType"] = "text/markdown"
            result["fileName"] = f"{report_type.casefold().replace(' ', '-')}-{review_id}.md"
            result["content"] = markdown
        return result

    def history(self, review_id: str, *, search: str = "") -> dict[str, Any]:
        review = self.get(review_id)
        entries = [
            *[{**item, "recordType": "Decision"} for item in review.get("decisions") or []],
            *[{**item, "recordType": "Comment", "timestamp": item.get("createdAt")} for item in review.get("comments") or []],
            *[{**item, "recordType": "ChangeRequest", "timestamp": item.get("createdAt")} for item in review.get("changeRequests") or []],
        ]
        query = search.casefold().strip()
        if query:
            entries = [item for item in entries if query in str(item).casefold()]
        entries.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        return {"reviewId": review_id, "history": entries, "count": len(entries)}

    def _dashboard(self, review: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(review)
        value["stale"] = int(review.get("proposalVersion") or 0) != int(proposal.get("version") or 0)
        value["readiness"] = self._readiness(review, proposal)
        value["proposalSummary"] = {
            "title": proposal.get("title"),
            "executiveSummary": proposal.get("executiveSummary"),
            "businessGoal": proposal.get("businessGoal"),
            "proposalVersion": proposal.get("version"),
            "contextVersion": proposal.get("contextVersion") or proposal.get("contextId"),
            "knowledgeVersion": proposal.get("knowledgeVersion"),
            "recommendationVersion": _recommendation_version(proposal),
            "approvalStatus": proposal.get("status"),
            "riskScore": (proposal.get("health") or {}).get("risk"),
            "readiness": (proposal.get("health") or {}).get("overallHealth"),
            "validationStatus": (proposal.get("validation") or {}).get("status"),
            "estimatedEffort": (proposal.get("estimate") or {}).get("engineeringDays"),
            "storyPoints": (proposal.get("estimate") or {}).get("storyPoints"),
            "affectedRepositories": review.get("affectedRepositories") or [],
            "affectedTeams": review.get("affectedTeams") or [],
        }
        value["currentStage"] = deepcopy(self._current_stage(review, required=False) or {})
        value["synchronization"] = self.authorize_synchronization(proposal["proposalId"]) if review.get("status") == "Approved" else {
            "authorized": False, "status": "Blocked",
            "reasons": ["Engineering Review must receive final approval."],
        }
        return value

    def _readiness(
        self,
        review: dict[str, Any],
        proposal: dict[str, Any],
        *,
        final: bool = False,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        validation = proposal.get("validation") or {}
        active_nodes = [node for node in proposal.get("nodes") or [] if node.get("status") != "Rejected"]
        stories = [node for node in active_nodes if node.get("type") == "Story"]
        tasks = [node for node in active_nodes if node.get("type") in {"Task", "Sub Task"}]
        if not validation.get("mandatoryPassed"):
            blockers.append("Planning Proposal validation has mandatory failures.")
        if any(not node.get("acceptanceCriteria") for node in stories):
            blockers.append("Every Story must have approved Acceptance Criteria.")
        if any(not any(task.get("parentId") == story.get("nodeId") for task in tasks) for story in stories):
            blockers.append("Every Story must have at least one implementation Task.")
        if any(
            item.get("status") != "Approved"
            for item in proposal.get("acceptanceCriteria") or []
        ):
            blockers.append("AI-suggested Acceptance Criteria require approval.")
        if any(item.get("status") == "Open" for item in review.get("changeRequests") or []):
            blockers.append("Open change requests must be resolved.")
        if _has_unresolved_dependencies(proposal):
            blockers.append("Dependencies are unresolved.")
        repository_complete = all(
            (node.get("repositoryMapping") or {}).get("repositoryId")
            or (node.get("repositoryMapping") or {}).get("repositoryName")
            for node in stories
        ) if stories else True
        if not repository_complete:
            blockers.append("Repository mapping is incomplete.")
        if any(item.get("status") == "Open" for item in review.get("comments") or []):
            warnings.append("Open review comments remain.")
        approved_stages = {
            stage.get("stageId") for stage in review.get("stages") or []
            if stage.get("status") == "Approved"
        }
        if final:
            required = {
                stage.get("stageId") for stage in review.get("stages") or []
                if stage.get("required")
            }
            if required - approved_stages:
                blockers.append("All required approval stages must be completed.")
            architecture = next((item for item in review.get("sections") or [] if item.get("name") == "Architecture Review"), {})
            risk = next((item for item in review.get("sections") or [] if item.get("name") == "Risk Review"), {})
            if architecture.get("status") != "Approved":
                blockers.append("Architecture approval is required.")
            if risk.get("status") != "Approved":
                blockers.append("Risk acceptance is required.")
        return {
            "status": "Ready" if not blockers else "Blocked",
            "approvalAllowed": not blockers,
            "stageApprovalAllowed": not blockers,
            "blockers": _unique(blockers),
            "warnings": _unique(warnings),
            "checks": {
                "duplicates": not any(item.get("code") == "duplicate_sibling" for item in validation.get("findings") or []),
                "orphanTasks": not any(item.get("code") == "orphan_story" for item in validation.get("findings") or []),
                "acceptanceCriteriaApproved": not any("Acceptance Criteria" in item for item in blockers),
                "validationPassed": bool(validation.get("mandatoryPassed")),
                "dependenciesResolved": "Dependencies are unresolved." not in blockers,
                "repositoryMappingComplete": repository_complete,
                "architectureApproved": any(
                    item.get("name") == "Architecture Review" and item.get("status") == "Approved"
                    for item in review.get("sections") or []
                ),
                "riskAccepted": any(
                    item.get("name") == "Risk Review" and item.get("status") == "Approved"
                    for item in review.get("sections") or []
                ),
            },
        }

    def _editable(self, review_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        values = self.store.read()
        review = values.get(review_id)
        if not isinstance(review, dict):
            raise LookupError("Engineering Review was not found.")
        if review.get("status") in TERMINAL_STATUSES:
            raise ValueError(f"Engineering Review is {review['status']} and cannot be changed.")
        if _expired(review.get("expiresAt")):
            review["status"] = "Expired"
            values[review_id] = review
            self.store.write(values)
            raise ValueError("Engineering Review has expired.")
        return review, values

    @staticmethod
    def _for_proposal(values: dict[str, Any], proposal_id: str) -> dict[str, Any] | None:
        items = [
            item for item in values.values()
            if isinstance(item, dict) and item.get("proposalId") == proposal_id
        ]
        return max(items, key=lambda item: int(item.get("proposalVersion") or 0), default=None)

    @staticmethod
    def _stage(review: dict[str, Any], stage_id: str) -> dict[str, Any]:
        stage = next((item for item in review.get("stages") or [] if item.get("stageId") == stage_id), None)
        if not stage:
            raise LookupError("Engineering Review stage was not found.")
        return stage

    def _current_stage(self, review: dict[str, Any], *, required: bool = True) -> dict[str, Any] | None:
        stage_id = _text(review.get("currentStageId"))
        stage = next((item for item in review.get("stages") or [] if item.get("stageId") == stage_id), None)
        if required and not stage:
            raise ValueError("Engineering Review has no active approval stage.")
        return stage

    @staticmethod
    def _next_stage(review: dict[str, Any], current: dict[str, Any]) -> dict[str, Any] | None:
        stages = sorted(review.get("stages") or [], key=lambda item: int(item.get("order") or 0))
        return next((item for item in stages if int(item.get("order") or 0) > int(current.get("order") or 0)), None)

    @staticmethod
    def _assert_reviewer(stage: dict[str, Any], actor: str, role: str) -> None:
        assigned = _text(stage.get("assignedReviewer"))
        if assigned and actor != assigned:
            raise PermissionError("This review stage is assigned to another reviewer.")
        if not assigned and _normalize(role) != _normalize(stage.get("role")):
            raise PermissionError(f"The current stage requires the {stage['role']} role.")

    @staticmethod
    def _assert_current_version(review: dict[str, Any], proposal: dict[str, Any]) -> None:
        if int(review.get("proposalVersion") or 0) != int(proposal.get("version") or 0):
            raise ValueError("Planning Proposal changed. Start a new Engineering Review for the current version.")

    @staticmethod
    def _approve_sections(review: dict[str, Any], stage: dict[str, Any], actor: str) -> None:
        mappings = {
            "Product Owner": {"Business Review", "Acceptance Criteria Review"},
            "Engineering Lead": {"Repository Review", "Dependency Review", "Estimate Review"},
            "Architect": {"Architecture Review", "Risk Review"},
            "QA Lead": {"Testing Review"},
            "Delivery Manager": {"Deployment Review"},
        }
        for section in review.get("sections") or []:
            if section.get("name") in mappings.get(stage.get("role"), set()):
                section["status"] = "Approved"
                section["approvedBy"] = actor
                section["approvedAt"] = _now()

    @staticmethod
    def _update_section_counts(review: dict[str, Any]) -> None:
        for section in review.get("sections") or []:
            section["commentCount"] = sum(
                1 for item in review.get("comments") or []
                if item.get("section") == section.get("name")
            )

    def _notify_reviewers(self, review: dict[str, Any], title: str, message: str) -> None:
        users = _unique([
            review.get("owner"),
            *[stage.get("assignedReviewer") for stage in review.get("stages") or []],
        ])
        if not users:
            self._notify(review, title, message, target_role="Engineering Manager")
        for user in users:
            self._notify(review, title, message, target_user=user)

    def _notify(
        self,
        review: dict[str, Any],
        title: str,
        message: str,
        *,
        target_user: str = "",
        target_role: str = "",
    ) -> None:
        if not self.platform:
            return
        self.platform.notifications.create({
            "type": "EngineeringReview",
            "title": title,
            "message": message,
            "severity": "Info",
            "source": "API",
            "correlationId": _text(review.get("correlationId")) or review["reviewId"],
            "targetUserId": target_user,
            "targetRole": target_role,
        })

    def _event(self, event_type: str, review: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "EngineeringReview",
            "correlationId": _text(review.get("correlationId")) or review["reviewId"],
            "payload": {
                "reviewId": review["reviewId"],
                "proposalId": review["proposalId"],
                "proposalVersion": review["proposalVersion"],
                "status": review["status"],
            },
        })

    def _audit(self, review: dict[str, Any], actor: str, action: str, reason: str) -> None:
        if not self.platform:
            return
        self.platform.audit.record({
            "action": action,
            "actor": actor,
            "source": "API",
            "targetType": "EngineeringReview",
            "targetId": review["reviewId"],
            "after": {
                "status": review.get("status"),
                "proposalVersion": review.get("proposalVersion"),
                "contextVersion": review.get("contextVersion"),
                "knowledgeVersion": review.get("knowledgeVersion"),
            },
            "reason": reason,
            "correlationId": _text(review.get("correlationId")) or review["reviewId"],
        })


def _stages(value: Any) -> list[dict[str, Any]]:
    source = value if isinstance(value, list) and value else [
        {"stageId": stage_id, "name": name, "role": role, "order": index + 1}
        for index, (stage_id, name, role) in enumerate(DEFAULT_APPROVAL_CHAIN)
    ]
    output = []
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            raise ValueError("Approval chain stages must be objects.")
        stage = ReviewStageDefinition(
            stageId=_text(item.get("stageId")) or f"stage-{index + 1}",
            name=_text(item.get("name")) or _text(item.get("role")) or f"Stage {index + 1}",
            role=_text(item.get("role")) or "Engineering Lead",
            order=int(item.get("order") or index + 1),
            required=bool(item.get("required", True)),
            assignedReviewer=_text(item.get("assignedReviewer")),
        ).__dict__
        stage.update({"status": "Pending", "approvedBy": "", "approvedAt": ""})
        output.append(stage)
    return sorted(output, key=lambda item: item["order"])


def _affected_repositories(proposal: dict[str, Any]) -> list[str]:
    return _unique([
        (node.get("repositoryMapping") or {}).get("repositoryName")
        or (node.get("repositoryMapping") or {}).get("repositoryId")
        for node in proposal.get("nodes") or []
        if node.get("status") != "Rejected"
    ])


def _affected_teams(proposal: dict[str, Any]) -> list[str]:
    return _unique([
        *[
            dependency.get("team") or dependency.get("owner")
            for dependency in (proposal.get("dependencyGraph") or {}).get("categories", {}).get("crossTeamDependencies", [])
            if isinstance(dependency, dict)
        ],
        *[node.get("owner") for node in proposal.get("nodes") or []],
    ])


def _recommendation_version(proposal: dict[str, Any]) -> int:
    return int(
        proposal.get("recommendationVersion")
        or (proposal.get("recommendedStrategy") or {}).get("version")
        or 1
    )


def _section_for_target(target_type: str) -> str:
    return {
        "Epic": "Business Review",
        "Feature": "Business Review",
        "Story": "Acceptance Criteria Review",
        "Task": "Testing Review",
        "Acceptance Criterion": "Acceptance Criteria Review",
        "Engineering Note": "Architecture Review",
        "Estimate": "Estimate Review",
        "Dependency": "Dependency Review",
        "Repository Mapping": "Repository Review",
    }.get(target_type, "Business Review")


def _has_unresolved_dependencies(proposal: dict[str, Any]) -> bool:
    node_ids = {
        node.get("nodeId") for node in proposal.get("nodes") or []
        if node.get("status") != "Rejected"
    }
    return any(
        edge.get("from") not in node_ids or edge.get("to") not in node_ids
        for edge in proposal.get("dependencies") or []
    )


def _markdown_report(review: dict[str, Any], report_type: str) -> str:
    summary = review.get("proposalSummary") or {}
    lines = [
        f"# {report_type}",
        "",
        f"**Proposal:** {summary.get('title') or review.get('proposalId')}",
        f"**Review Status:** {review.get('status')}",
        f"**Proposal Version:** {review.get('proposalVersion')}",
        f"**Context Version:** {review.get('contextVersion')}",
        f"**Knowledge Version:** {review.get('knowledgeVersion') or 'Not versioned'}",
        f"**Validation:** {summary.get('validationStatus')}",
        f"**Readiness:** {(review.get('readiness') or {}).get('status')}",
        "",
    ]
    if report_type in {"Review Report", "Planning Summary"}:
        lines.extend(["## Summary", summary.get("executiveSummary") or "No executive summary.", ""])
    if report_type in {"Review Report", "Architecture Summary"}:
        lines.append("## Review Sections")
        lines.extend(
            f"- {item.get('name')}: {item.get('status')} ({item.get('commentCount', 0)} comments)"
            for item in review.get("sections") or []
        )
        lines.append("")
    if report_type in {"Review Report", "Approval Report", "Decision Log"}:
        lines.append("## Decisions")
        lines.extend(
            f"- {item.get('timestamp')}: {item.get('reviewer')} - {item.get('decision')} ({item.get('stage')})"
            for item in review.get("decisions") or []
        )
        lines.append("")
    if review.get("changeRequests"):
        lines.append("## Change Requests")
        lines.extend(
            f"- {item.get('type')}: {item.get('description')} [{item.get('status')}]"
            for item in review["changeRequests"]
        )
    return "\n".join(lines).strip() + "\n"


def _simple_pdf(markdown: str) -> bytes:
    lines = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in markdown.splitlines()[:48]
    ]
    commands = ["BT", "/F1 10 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -14 Td")
        commands.append(f"({line[:110]}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(payload)


def _required(value: dict[str, Any], key: str) -> str:
    result = _text(value.get(key))
    if not result:
        raise ValueError(f"{key} is required.")
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize(value: Any) -> str:
    return _text(value).replace("_", " ").replace("-", " ").casefold()


def _digest(value: Any) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        clean = _text(value)
        if clean and clean not in output:
            output.append(clean)
    return output


def _expired(value: Any) -> bool:
    raw = _text(value)
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except ValueError:
        return False


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
