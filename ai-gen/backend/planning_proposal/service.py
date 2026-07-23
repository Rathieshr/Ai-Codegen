"""Deterministic, editable Planning Proposal Engine."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.platform.shared import JsonMapStore

from .models import (
    PlanningProposal,
    ProposalDiff,
    ProposalEstimate,
    ProposalHealth,
    ProposalNode,
    ProposalReview,
    ProposalTraceability,
    ProposalValidation,
)


NODE_TYPES = ("Epic", "Feature", "Story", "Task", "Sub Task")
PARENT_TYPES = {"Epic": "", "Feature": "Epic", "Story": "Feature", "Task": "Story", "Sub Task": "Task"}
TASK_TYPES = {
    "Frontend", "Backend", "API", "Database", "Repository", "Infrastructure", "Testing",
    "Automation", "Documentation", "Deployment", "DevOps", "Security", "Architecture",
}
STATUSES = {"Draft", "Review", "Approved", "Published", "Archived"}


class PlanningProposalService:
    """Turns an approved recommendation into a safe HEI working draft."""

    def __init__(
        self,
        store: JsonMapStore,
        *,
        recommendation_service: Any,
        planning_context_service: Any,
        requirement_planning_service: Any,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.recommendation_service = recommendation_service
        self.planning_context_service = planning_context_service
        self.requirement_planning_service = requirement_planning_service
        self.platform = platform

    def build(self, request: dict[str, Any]) -> dict[str, Any]:
        recommendation_id = _required(request, "recommendationId")
        recommendation = self.recommendation_service.get(recommendation_id)
        context = self.planning_context_service.require_reviewed(
            recommendation["contextId"], recommendation["requirementId"],
        )
        recommendation = self.recommendation_service.require_approved(recommendation_id, context["contextId"])
        values = self.store.read()
        existing = _for_recommendation(values, recommendation_id)
        if existing and request.get("force") is not True:
            return existing

        actor = _text(request.get("actor")) or "HEI User"
        generated = self.requirement_planning_service.generate({
            "requirementId": recommendation["requirementId"],
            "planningContextId": context["contextId"],
            "recommendationId": recommendation_id,
            "actor": actor,
            "force": bool(request.get("force")),
        })
        version = int((existing or {}).get("version") or 0) + 1
        proposal = self._assemble(generated, context, recommendation, actor, version, existing)
        values[proposal["proposalId"]] = proposal
        self.store.write(values)
        self._publish("PlanningProposalGenerated", proposal)
        return proposal

    def get(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.read().get(proposal_id)
        if not isinstance(proposal, dict):
            raise LookupError("Planning Proposal was not found.")
        return proposal

    def update(self, proposal_id: str, request: dict[str, Any]) -> dict[str, Any]:
        actor = _text(request.get("actor")) or "HEI User"
        reason = _text(request.get("reason")) or "Planning Proposal edited."
        proposal, values = self._editable(proposal_id, request)
        previous = _snapshot(proposal)
        changes: list[str] = []
        action = _text(request.get("operation") or request.get("action") or "edit").casefold()
        if action == "rollback":
            proposal = self._rollback(proposal, request)
            changes.append(f"Rolled back to version {request.get('targetVersion')}.")
        elif action in {"move", "delete", "duplicate", "merge", "split", "approve", "reject"}:
            changes.extend(self._node_operation(proposal, action, request))
        else:
            changes.extend(self._apply_edits(proposal, request))
        proposal = self._version(proposal, previous, actor, reason, changes)
        proposal = self._recalculate(proposal)
        values[proposal_id] = proposal
        self.store.write(values)
        self._publish("PlanningProposalUpdated", proposal)
        return proposal

    def regenerate(self, request: dict[str, Any]) -> dict[str, Any]:
        proposal_id = _required(request, "proposalId")
        scope = _text(request.get("scope") or "Entire Proposal")
        if scope.casefold() == "entire proposal":
            current = self.get(proposal_id)
            return self.build({
                "recommendationId": current["recommendationId"],
                "actor": _text(request.get("actor")) or "HEI User",
                "force": True,
            })
        proposal, values = self._editable(proposal_id, request)
        previous = _snapshot(proposal)
        changes = self._regenerate_scope(proposal, scope, request)
        proposal = self._version(
            proposal, previous, _text(request.get("actor")) or "HEI User",
            _text(request.get("reason")) or f"Regenerated {scope}.", changes,
        )
        proposal = self._recalculate(proposal)
        values[proposal_id] = proposal
        self.store.write(values)
        self._publish("PlanningProposalRegenerated", proposal)
        return proposal

    def validate(self, request: dict[str, Any]) -> dict[str, Any]:
        proposal_id = _required(request, "proposalId")
        values = self.store.read()
        proposal = self.get(proposal_id)
        validation, health = _validate(proposal)
        proposal["validation"] = validation
        proposal["health"] = health
        proposal["updatedAt"] = _now()
        values[proposal_id] = proposal
        self.store.write(values)
        self._publish("PlanningProposalValidated", proposal)
        return proposal

    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        proposal = self.validate(request)
        proposal_id = proposal["proposalId"]
        actor = _required(request, "actor")
        checklist = _review_checklist(proposal)
        complete = all(item["passed"] for item in checklist if item["mandatory"])
        proposal["review"] = {
            "status": "Completed" if complete else "NeedsChanges",
            "checklist": checklist,
            "reviewer": actor,
            "comments": _text(request.get("comments")),
            "reviewedAt": _now(),
        }
        proposal["status"] = "Review"
        proposal["updatedAt"] = _now()
        values = self.store.read()
        values[proposal_id] = proposal
        self.store.write(values)
        self._publish("PlanningProposalReviewed", proposal)
        return proposal

    def approve(self, request: dict[str, Any]) -> dict[str, Any]:
        proposal = self.validate(request)
        if not proposal.get("validation", {}).get("mandatoryPassed"):
            raise ValueError("Planning Proposal cannot be approved until mandatory validation findings are resolved.")
        if proposal.get("review", {}).get("status") != "Completed":
            raise ValueError("Complete the Planning Proposal review checklist before approval.")
        actor = _required(request, "actor")
        proposal["status"] = "Approved"
        proposal["approvedBy"] = actor
        proposal["approvedAt"] = _now()
        proposal["updatedAt"] = proposal["approvedAt"]
        for node in proposal.get("nodes") or []:
            if node.get("status") != "Rejected":
                node["status"] = "Approved"
        values = self.store.read()
        values[proposal["proposalId"]] = proposal
        self.store.write(values)
        self._publish("PlanningProposalApproved", proposal)
        return proposal

    def history(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get(proposal_id)
        return {
            "proposalId": proposal_id,
            "currentVersion": proposal["version"],
            "status": proposal["status"],
            "history": proposal.get("history") or [],
            "count": len(proposal.get("history") or []),
        }

    def _assemble(
        self,
        generated: dict[str, Any],
        context: dict[str, Any],
        recommendation: dict[str, Any],
        actor: str,
        version: int,
        existing: dict[str, Any] | None,
    ) -> dict[str, Any]:
        legacy = generated.get("planningProposal") or {}
        legacy_items = list(legacy.get("items") or [])
        legacy_changes = list(legacy.get("changes") or [])
        requirement = context.get("requirement") or {}
        proposal_id = _text((existing or {}).get("proposalId")) or "planning-proposal-" + _digest([
            recommendation["recommendationId"], recommendation["version"], context["contextVersion"],
        ])
        item_by_key = {
            (_text(item.get("type")), _text(item.get("title"))): item
            for item in legacy_items if isinstance(item, dict)
        }
        nodes: list[dict[str, Any]] = []
        title_ids: dict[tuple[str, str], str] = {}
        for order, change in enumerate(legacy_changes):
            kind = _type(change.get("artifactType"))
            if kind not in NODE_TYPES:
                continue
            title = _text(change.get("title")) or f"Untitled {kind}"
            item = item_by_key.get((kind, title), {})
            node_id = "proposal-node-" + _digest([proposal_id, kind, title, order])
            title_ids[(kind, title)] = node_id
            nodes.append(self._node(
                proposal_id, node_id, "", kind, title, item, change, context, recommendation, version, order,
            ))
        if not nodes:
            raise ValueError("The approved recommendation did not produce an editable planning hierarchy.")

        for node, change in zip(nodes, [item for item in legacy_changes if _type(item.get("artifactType")) in NODE_TYPES]):
            parent_title = _text(change.get("parentTitle"))
            parent_type = PARENT_TYPES.get(node["type"], "")
            node["parentId"] = title_ids.get((parent_type, parent_title), "")
            if node["type"] != "Epic" and not node["parentId"]:
                node["parentId"] = _nearest_parent(nodes, node["type"])

        self._ensure_story_tasks(proposal_id, nodes, context, recommendation, version)
        estimate = _proposal_estimate(generated.get("engineeringEstimation") or {}, recommendation)
        _distribute_estimate(nodes, estimate)
        dependency_edges = _dependency_edges(nodes)
        implementation_order = _implementation_order(nodes, dependency_edges)
        now = _now()
        proposal = PlanningProposal(
            proposalId=proposal_id,
            planningPackId=_text(generated.get("planningPackId")),
            requirementId=recommendation["requirementId"],
            contextId=context["contextId"],
            contextVersion=context["contextVersion"],
            recommendationId=recommendation["recommendationId"],
            recommendationVersion=int(recommendation["version"]),
            projectId=_text(recommendation.get("projectId")),
            correlationId=_text(recommendation.get("correlationId") or generated.get("correlationId")),
            title=_text(requirement.get("title")) or "Planning Proposal",
            status="Draft",
            version=version,
            nodes=[ProposalNode(**node) for node in nodes],
            estimate=ProposalEstimate(**estimate),
            implementationOrder=implementation_order,
            dependencies=dependency_edges,
            validation=ProposalValidation(status="Pending", mandatoryPassed=False, findings=[], checkedAt=""),
            health=ProposalHealth(
                overallHealth=0, coverage=0, estimateCompleteness=0, repositoryCoverage=0,
                requirementCoverage=0, engineeringConfidence=int(recommendation["confidence"]["engineering"]),
                planningConfidence=int(recommendation["confidence"]["planning"]), risk=recommendation["impact"]["riskLevel"],
            ),
            diff=ProposalDiff(**_proposal_diff(proposal_id, recommendation, nodes, estimate)),
            review=ProposalReview(status="Pending", checklist=[]),
            author=actor,
            createdAt=_text((existing or {}).get("createdAt")) or now,
            updatedAt=now,
            history=[],
        ).to_dict()
        previous_history = list((existing or {}).get("history") or [])
        if existing:
            previous_history.append(_history_entry(existing, actor, "Entire proposal regenerated.", ["Regenerated proposal hierarchy."]))
        proposal["history"] = previous_history
        return self._recalculate(proposal)

    def _node(
        self,
        proposal_id: str,
        node_id: str,
        parent_id: str,
        kind: str,
        title: str,
        item: dict[str, Any],
        change: dict[str, Any],
        context: dict[str, Any],
        recommendation: dict[str, Any],
        version: int,
        order: int,
    ) -> dict[str, Any]:
        requirement = context.get("requirement") or {}
        impact = recommendation.get("impact") or {}
        criteria = _strings(item.get("acceptanceCriteria"))
        if kind == "Story" and not criteria:
            criteria = _strings(requirement.get("acceptanceCriteria"))
        business_goals = _strings(requirement.get("businessGoals"))
        functional = _strings(requirement.get("functionalRequirements"))
        modules = _strings(impact.get("affectedModules"))
        memory = [
            _text(entry.get("id") or entry.get("title"))
            for entry in context.get("memory", {}).get("matches") or []
        ]
        traceability = ProposalTraceability(
            requirementId=recommendation["requirementId"],
            businessGoals=business_goals,
            functionalRequirements=functional,
            acceptanceCriteria=criteria,
            recommendationId=recommendation["recommendationId"],
            repositoryModules=modules,
            memoryReferences=_unique(memory),
        )
        confidence = int(change.get("confidence") or recommendation.get("confidence", {}).get("overall") or 0)
        description = _text(item.get("description")) or _text(change.get("reason"))
        return ProposalNode(
            nodeId=node_id,
            proposalId=proposal_id,
            parentId=parent_id,
            type=kind,
            title=title,
            description=description,
            businessValue=business_goals[0] if business_goals else recommendation.get("impact", {}).get("businessImpact", ""),
            acceptanceCriteria=criteria,
            businessRules=_strings(requirement.get("businessRules")),
            dependencies=_strings(requirement.get("dependencies")),
            estimate={"engineeringDays": 0.0, "storyPoints": 0, "confidence": confidence},
            storyPoints=0,
            repositoryModules=modules,
            affectedApis=_strings(impact.get("affectedApis")),
            affectedScreens=_strings(impact.get("affectedScreens")),
            technicalNotes=_unique([
                recommendation.get("expectedRepositoryImpact", ""),
                *recommendation.get("engineeringReasoning", []),
            ]),
            generatedTests=_suggested_tests(kind, criteria, impact),
            risk=_text(impact.get("riskLevel")) or "Medium",
            priority="High" if _text(impact.get("riskLevel")) in {"High", "Critical"} else "Medium",
            origin="AI Suggested",
            confidence=confidence,
            reason=_text(change.get("reason")) or "Derived from the approved Planning Recommendation.",
            repositoryMapping={
                "repositoryId": _text(impact.get("repositoryId")),
                "repositoryName": _text(impact.get("repositoryName")),
                "modules": modules,
                "apis": _strings(impact.get("affectedApis")),
                "screens": _strings(impact.get("affectedScreens")),
                "evidenceStatus": "Mapped" if modules or impact.get("repositoryId") else "Missing",
            },
            traceability=traceability,
            planningVersion=version,
            status="Draft",
            order=order,
        ).__dict__

    def _ensure_story_tasks(
        self,
        proposal_id: str,
        nodes: list[dict[str, Any]],
        context: dict[str, Any],
        recommendation: dict[str, Any],
        version: int,
    ) -> None:
        stories = [node for node in nodes if node["type"] == "Story"]
        existing_parent_ids = {node["parentId"] for node in nodes if node["type"] in {"Task", "Sub Task"}}
        for story in stories:
            if story["nodeId"] in existing_parent_ids:
                continue
            for task in _task_blueprints(story, recommendation):
                order = len(nodes)
                node_id = "proposal-node-" + _digest([proposal_id, story["nodeId"], task["type"], order])
                traceability = deepcopy(story["traceability"])
                nodes.append(ProposalNode(
                    nodeId=node_id,
                    proposalId=proposal_id,
                    parentId=story["nodeId"],
                    type="Task",
                    title=task["title"],
                    description=task["description"],
                    businessValue=story["businessValue"],
                    acceptanceCriteria=story["acceptanceCriteria"],
                    businessRules=story["businessRules"],
                    dependencies=[],
                    estimate={"engineeringDays": 0.0, "storyPoints": 0, "confidence": story["confidence"]},
                    storyPoints=0,
                    repositoryModules=story["repositoryModules"],
                    affectedApis=story["affectedApis"],
                    affectedScreens=story["affectedScreens"],
                    technicalNotes=story["technicalNotes"],
                    generatedTests=task["tests"],
                    risk=story["risk"],
                    priority=story["priority"],
                    origin="AI Suggested",
                    confidence=story["confidence"],
                    reason="Task breakdown derived from the approved Story scope and repository mapping.",
                    repositoryMapping=deepcopy(story["repositoryMapping"]),
                    traceability=traceability,
                    planningVersion=version,
                    status="Draft",
                    taskType=task["type"],
                    order=order,
                ).__dict__)

    def _editable(self, proposal_id: str, request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        values = self.store.read()
        proposal = self.get(proposal_id)
        if proposal.get("status") in {"Approved", "Published", "Archived"}:
            raise ValueError("Approved, Published, or Archived proposals are immutable. Create a new version first.")
        expected = request.get("expectedVersion")
        if expected is not None and int(expected) != int(proposal.get("version") or 0):
            raise ValueError("Planning Proposal changed. Reload before editing.")
        return proposal, values

    def _apply_edits(self, proposal: dict[str, Any], request: dict[str, Any]) -> list[str]:
        changes: list[str] = []
        node_changes = list(request.get("nodeChanges") or [])
        if request.get("nodeId"):
            node_changes.append({**dict(request.get("changes") or {}), "nodeId": request["nodeId"]})
        for patch in node_changes:
            node = _node(proposal, _required(patch, "nodeId"))
            for key in (
                "title", "description", "businessValue", "acceptanceCriteria", "businessRules", "dependencies",
                "storyPoints", "repositoryModules", "affectedApis", "affectedScreens", "technicalNotes",
                "generatedTests", "risk", "priority", "owner", "taskType",
            ):
                if key in patch:
                    if key == "taskType" and patch[key] and patch[key] not in TASK_TYPES:
                        raise ValueError(f"taskType must be one of: {', '.join(sorted(TASK_TYPES))}.")
                    node[key] = deepcopy(patch[key])
                    changes.append(f"Updated {node['type']} {node['title']} field {key}.")
            node["origin"] = "User Edited"
            node["status"] = "Draft"
        estimate_patch = request.get("estimate")
        if isinstance(estimate_patch, dict):
            reason = _text(estimate_patch.get("overrideReason"))
            if not reason:
                raise ValueError("overrideReason is required for estimate changes.")
            for key in ("engineeringDays", "storyPoints", "sprintCount", "developersRequired", "complexity", "risk"):
                if key in estimate_patch:
                    proposal["estimate"][key] = estimate_patch[key]
            proposal["estimate"]["overrideReason"] = reason
            changes.append("Overrode the engineering estimate.")
        if request.get("status") in STATUSES:
            proposal["status"] = request["status"]
            changes.append(f"Changed proposal status to {request['status']}.")
        return changes or ["Saved Planning Proposal draft."]

    def _node_operation(self, proposal: dict[str, Any], action: str, request: dict[str, Any]) -> list[str]:
        nodes = proposal["nodes"]
        node = _node(proposal, _required(request, "nodeId"))
        if action in {"approve", "reject"}:
            status = "Approved" if action == "approve" else "Rejected"
            affected = {node["nodeId"]}
            if action == "reject":
                affected.update(_descendants(node["nodeId"], nodes))
            for item in nodes:
                if item["nodeId"] in affected:
                    item["status"] = status
            return [f"{status} {node['type']} {node['title']} and {len(affected) - 1} descendant(s)."]
        if action == "move":
            parent_id = _text(request.get("parentId"))
            _validate_parent(node, parent_id, nodes)
            node["parentId"] = parent_id
            node["order"] = max(0, int(request.get("order") or 0))
            return [f"Moved {node['type']} {node['title']}."]
        if action == "delete":
            descendant_ids = _descendants(node["nodeId"], nodes)
            proposal["nodes"] = [item for item in nodes if item["nodeId"] not in {node["nodeId"], *descendant_ids}]
            return [f"Deleted {node['type']} {node['title']} and {len(descendant_ids)} descendant(s)."]
        if action == "duplicate":
            clone = deepcopy(node)
            clone["nodeId"] = "proposal-node-" + _digest([proposal["proposalId"], node["nodeId"], proposal["version"], len(nodes)])
            clone["title"] = _text(request.get("title")) or f"{node['title']} Copy"
            clone["origin"] = "User Edited"
            clone["order"] = len(nodes)
            nodes.append(clone)
            return [f"Duplicated {node['type']} {node['title']}."]
        if action == "split":
            if node["type"] not in {"Feature", "Story", "Task"}:
                raise ValueError("Only Features, Stories, and Tasks can be split.")
            titles = _strings(request.get("titles"))
            if len(titles) < 2:
                raise ValueError("Split requires at least two titles.")
            node["title"] = titles[0]
            for title in titles[1:]:
                clone = deepcopy(node)
                clone["nodeId"] = "proposal-node-" + _digest([proposal["proposalId"], node["nodeId"], title])
                clone["title"] = title
                clone["origin"] = "User Edited"
                clone["order"] = len(nodes)
                nodes.append(clone)
            return [f"Split {node['type']} into {len(titles)} items."]
        merge_ids = _strings(request.get("mergeNodeIds"))
        if len(merge_ids) < 2:
            raise ValueError("Merge requires at least two node IDs.")
        selected = [_node(proposal, node_id) for node_id in merge_ids]
        if len({item["type"] for item in selected}) != 1:
            raise ValueError("Only nodes of the same type can be merged.")
        target = selected[0]
        target["title"] = _text(request.get("title")) or target["title"]
        for key in ("acceptanceCriteria", "businessRules", "dependencies", "technicalNotes", "generatedTests"):
            target[key] = _unique([value for item in selected for value in _strings(item.get(key))])
        removed = set(merge_ids[1:])
        proposal["nodes"] = [item for item in nodes if item["nodeId"] not in removed]
        for item in proposal["nodes"]:
            if item.get("parentId") in removed:
                item["parentId"] = target["nodeId"]
        return [f"Merged {len(selected)} {target['type']} items."]

    def _regenerate_scope(self, proposal: dict[str, Any], scope: str, request: dict[str, Any]) -> list[str]:
        normalized = scope.casefold()
        if normalized in {"engineering estimate", "estimate"}:
            proposal["estimate"]["engineeringDays"] = proposal["estimate"]["aiEngineeringDays"]
            proposal["estimate"]["storyPoints"] = proposal["estimate"]["aiStoryPoints"]
            proposal["estimate"]["overrideReason"] = ""
            return ["Regenerated Engineering Estimate."]
        node = _node(proposal, _required(request, "nodeId"))
        if normalized in {"acceptance criteria", "acceptance"}:
            node["acceptanceCriteria"] = _unique(node["traceability"]["acceptanceCriteria"])
        elif normalized in {"dependencies", "dependency"}:
            node["dependencies"] = _unique(_strings(node["traceability"].get("functionalRequirements")))
        elif normalized in {"task breakdown", "tasks"}:
            child_ids = {item["nodeId"] for item in proposal["nodes"] if item["parentId"] == node["nodeId"] and item["type"] == "Task"}
            proposal["nodes"] = [item for item in proposal["nodes"] if item["nodeId"] not in child_ids]
            self._ensure_story_tasks(proposal["proposalId"], proposal["nodes"], {"requirement": {}}, {
                "impact": {
                    "affectedModules": node["repositoryModules"], "affectedApis": node["affectedApis"],
                    "affectedScreens": node["affectedScreens"], "riskLevel": node["risk"],
                },
                "confidence": {"overall": node["confidence"]},
                "recommendationId": proposal["recommendationId"],
                "engineeringReasoning": node["technicalNotes"],
                "expectedRepositoryImpact": "",
            }, proposal["version"] + 1)
        else:
            node["confidence"] = min(98, max(node["confidence"], 75))
            node["reason"] = f"Regenerated only this {node['type']} from its existing traceability boundary."
            node["origin"] = "AI Suggested"
        return [f"Regenerated {scope} for {node['title']}."]

    def _rollback(self, proposal: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        target = int(request.get("targetVersion") or 0)
        version = next((item for item in proposal.get("history") or [] if int(item.get("version") or 0) == target), None)
        if not version:
            raise LookupError(f"Planning Proposal version {target} was not found.")
        restored = deepcopy(version.get("snapshot") or {})
        if not restored:
            raise ValueError("Selected Planning Proposal version has no restorable snapshot.")
        restored["proposalId"] = proposal["proposalId"]
        restored["history"] = proposal.get("history") or []
        restored["version"] = proposal["version"]
        restored["status"] = "Draft"
        return restored

    def _version(
        self,
        proposal: dict[str, Any],
        previous: dict[str, Any],
        actor: str,
        reason: str,
        changes: list[str],
    ) -> dict[str, Any]:
        history = list(proposal.get("history") or [])
        history.append(_history_entry(previous, actor, reason, changes))
        proposal["history"] = history
        proposal["version"] = int(previous.get("version") or 0) + 1
        proposal["status"] = "Draft"
        proposal["approvedBy"] = ""
        proposal["approvedAt"] = ""
        proposal["review"] = {"status": "Pending", "checklist": [], "reviewer": "", "comments": "", "reviewedAt": ""}
        proposal["updatedAt"] = _now()
        for node in proposal.get("nodes") or []:
            node["planningVersion"] = proposal["version"]
        return proposal

    def _recalculate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        proposal["dependencies"] = _dependency_edges(proposal.get("nodes") or [])
        proposal["implementationOrder"] = _implementation_order(proposal.get("nodes") or [], proposal["dependencies"])
        proposal["diff"] = _proposal_diff_from_record(proposal)
        validation, health = _validate(proposal)
        proposal["validation"] = validation
        proposal["health"] = health
        return proposal

    def _publish(self, event_type: str, proposal: dict[str, Any]) -> None:
        if not self.platform:
            return
        self.platform.events.publish({
            "eventType": event_type,
            "source": "PlanningProposalEngine",
            "projectId": proposal.get("projectId"),
            "correlationId": proposal.get("correlationId"),
            "payload": {
                "proposalId": proposal.get("proposalId"),
                "recommendationId": proposal.get("recommendationId"),
                "status": proposal.get("status"),
                "version": proposal.get("version"),
            },
        })


def _proposal_estimate(value: dict[str, Any], recommendation: dict[str, Any]) -> dict[str, Any]:
    effective = value.get("effectiveEstimate") or value.get("originalEstimate") or {}
    report = effective.get("report") or {}
    days = float(report.get("engineeringDays") or effective.get("engineeringDays") or 0)
    points = int(report.get("storyPoints") or effective.get("storyPoints") or 0)
    return {
        "aiEngineeringDays": days,
        "aiStoryPoints": points,
        "engineeringDays": days,
        "storyPoints": points,
        "sprintCount": float(report.get("estimatedSprintCount") or effective.get("estimatedSprintCount") or 1),
        "developersRequired": int(report.get("developersNeeded") or report.get("suggestedTeamSize") or effective.get("suggestedTeamSize") or 1),
        "complexity": _text(report.get("complexity") or effective.get("complexity") or recommendation.get("impact", {}).get("estimatedComplexity")) or "Medium",
        "risk": _text(report.get("risk") or effective.get("risk") or recommendation.get("impact", {}).get("riskLevel")) or "Medium",
        "confidence": int(report.get("confidence") or effective.get("confidence") or recommendation.get("confidence", {}).get("overall") or 0),
        "overrideReason": "",
    }


def _distribute_estimate(nodes: list[dict[str, Any]], estimate: dict[str, Any]) -> None:
    work = [node for node in nodes if node["type"] in {"Story", "Task", "Sub Task"}]
    if not work:
        return
    per_days = round(float(estimate["engineeringDays"]) / len(work), 2)
    per_points = max(1, round(int(estimate["storyPoints"]) / len(work))) if estimate["storyPoints"] else 0
    for node in work:
        node["estimate"] = {
            "engineeringDays": per_days,
            "storyPoints": per_points,
            "confidence": estimate["confidence"],
            "source": "AI Estimate",
        }
        node["storyPoints"] = per_points


def _task_blueprints(story: dict[str, Any], recommendation: dict[str, Any]) -> list[dict[str, Any]]:
    blueprints = []
    if story.get("affectedScreens"):
        blueprints.append(("Frontend", "Implement user experience", "Implement the approved interaction states and screen behavior."))
    if story.get("affectedApis"):
        blueprints.append(("API", "Implement API behavior", "Implement bounded API behavior and validation for mapped acceptance criteria."))
    if story.get("repositoryModules"):
        blueprints.append(("Backend", "Implement domain behavior", "Implement the approved behavior in evidence-matched repository modules."))
    blueprints.append(("Testing", "Add verification coverage", "Add functional, negative, permission, integration, and regression tests required by the Story."))
    if not any(item[0] in {"Frontend", "API", "Backend"} for item in blueprints):
        blueprints.insert(0, ("Architecture", "Locate implementation boundary", "Confirm the closest existing implementation before making scoped changes."))
    return [
        {
            "type": kind,
            "title": f"{title}: {story['title']}",
            "description": description,
            "tests": _suggested_tests("Task", story.get("acceptanceCriteria") or [], recommendation.get("impact") or {}),
        }
        for kind, title, description in blueprints
    ]


def _suggested_tests(kind: str, criteria: list[str], impact: dict[str, Any]) -> list[str]:
    if kind not in {"Story", "Task", "Sub Task"}:
        return []
    tests = [f"Verify: {criterion}" for criterion in criteria[:5]]
    tests.extend(["Validate negative and error handling paths.", "Run regression coverage for affected modules."])
    if impact.get("affectedApis"):
        tests.append("Validate API integration and contract behavior.")
    return _unique(tests)


def _dependency_edges(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = {node["nodeId"] for node in nodes}
    by_title = {node["title"].casefold(): node["nodeId"] for node in nodes}
    edges = []
    for node in nodes:
        for dependency in _strings(node.get("dependencies")):
            dependency_id = dependency if dependency in ids else by_title.get(dependency.casefold(), "")
            if dependency_id and dependency_id != node["nodeId"]:
                edges.append({"from": node["nodeId"], "to": dependency_id, "type": "DependsOn"})
    return _unique_dicts(edges)


def _implementation_order(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    dependencies = {node["nodeId"]: set() for node in nodes}
    for edge in edges:
        dependencies.setdefault(edge["from"], set()).add(edge["to"])
    ordered: list[str] = []
    remaining = set(dependencies)
    while remaining:
        ready = sorted(
            [node_id for node_id in remaining if not (dependencies[node_id] & remaining)],
            key=lambda node_id: next((int(node.get("order") or 0) for node in nodes if node["nodeId"] == node_id), 0),
        )
        if not ready:
            ready = sorted(remaining)
        for node_id in ready:
            ordered.append(node_id)
            remaining.remove(node_id)
    return ordered


def _proposal_diff(
    proposal_id: str,
    recommendation: dict[str, Any],
    nodes: list[dict[str, Any]],
    estimate: dict[str, Any],
) -> dict[str, Any]:
    recommendation_changes = {
        (_text(item.get("artifactType")), _text(item.get("title"))): item
        for item in recommendation.get("diff", {}).get("operations") or []
    }
    changes = []
    for node in nodes:
        source = recommendation_changes.get((node["type"], node["title"]), {})
        action = _text(source.get("action")) or ("Created" if node["origin"] == "AI Suggested" else "Modified")
        if action == "Create":
            action = "Created"
        elif action == "Modify":
            action = "Modified"
        elif action == "Reuse":
            action = "Reused"
        changes.append({
            "nodeId": node["nodeId"], "action": action, "type": node["type"], "title": node["title"],
            "reason": node["reason"], "confidence": node["confidence"],
        })
    summary = {
        action: sum(1 for item in changes if item["action"] == action)
        for action in ("Created", "Modified", "Merged", "Split", "Deleted", "Reused")
    }
    return {
        "diffId": "proposal-diff-" + _digest([proposal_id, changes]),
        "recommendationId": recommendation["recommendationId"],
        "summary": summary,
        "changes": changes,
        "estimatedSprintImpact": f"{estimate['sprintCount']} sprint(s), {estimate['engineeringDays']} engineering day(s).",
    }


def _proposal_diff_from_record(proposal: dict[str, Any]) -> dict[str, Any]:
    prior = {
        item.get("nodeId"): item.get("action")
        for item in proposal.get("diff", {}).get("changes") or []
    }
    changes = []
    for node in proposal.get("nodes") or []:
        action = "Modified" if node.get("origin") == "User Edited" else prior.get(node["nodeId"]) or "Created"
        changes.append({
            "nodeId": node["nodeId"], "action": action, "type": node["type"], "title": node["title"],
            "reason": node.get("reason"), "confidence": node.get("confidence"),
        })
    summary = {
        action: sum(1 for item in changes if item["action"] == action)
        for action in ("Created", "Modified", "Merged", "Split", "Deleted", "Reused")
    }
    return {
        "diffId": "proposal-diff-" + _digest([proposal["proposalId"], proposal["version"], changes]),
        "recommendationId": proposal["recommendationId"],
        "summary": summary,
        "changes": changes,
        "estimatedSprintImpact": f"{proposal['estimate']['sprintCount']} sprint(s), {proposal['estimate']['engineeringDays']} engineering day(s).",
    }


def _validate(proposal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = list(proposal.get("nodes") or [])
    findings: list[dict[str, Any]] = []
    node_ids = {node.get("nodeId") for node in nodes}
    seen: dict[tuple[str, str, str], str] = {}
    for node in nodes:
        key = (node.get("type", ""), node.get("parentId", ""), _text(node.get("title")).casefold())
        if key in seen:
            _finding(findings, "duplicate_item", "Error", node, f"Duplicate {node.get('type')} title under the same parent.")
        seen[key] = node.get("nodeId", "")
        parent_type = PARENT_TYPES.get(node.get("type"), "")
        if parent_type:
            parent = next((item for item in nodes if item.get("nodeId") == node.get("parentId")), None)
            if not parent or parent.get("type") != parent_type:
                _finding(findings, "invalid_hierarchy", "Error", node, f"{node.get('type')} requires a {parent_type} parent.")
        if node.get("type") == "Story" and not _strings(node.get("acceptanceCriteria")):
            _finding(findings, "missing_acceptance_criteria", "Error", node, "Story requires measurable Acceptance Criteria.")
        if node.get("type") in {"Story", "Task", "Sub Task"} and not node.get("estimate", {}).get("engineeringDays"):
            _finding(findings, "missing_estimate", "Error", node, "Engineering estimate is required.")
        if node.get("type") == "Story" and not node.get("storyPoints"):
            _finding(findings, "missing_story_points", "Error", node, "Story Points are required.")
        if node.get("repositoryMapping", {}).get("evidenceStatus") == "Missing":
            _finding(findings, "missing_repository", "Warning", node, "Repository mapping requires review.")
        trace = node.get("traceability") or {}
        if not trace.get("requirementId") or not trace.get("recommendationId"):
            _finding(findings, "missing_traceability", "Error", node, "Requirement and recommendation traceability are required.")
    cycles = _dependency_cycles(proposal.get("dependencies") or [], node_ids)
    for node_id in cycles:
        _finding(findings, "circular_dependency", "Error", _node(proposal, node_id), "Circular dependency detected.")
    mandatory_passed = not any(item["severity"] == "Error" for item in findings)
    total = max(1, len(nodes))
    stories = [node for node in nodes if node.get("type") == "Story"]
    estimated = sum(1 for node in nodes if node.get("type") not in {"Epic", "Feature"} and node.get("estimate", {}).get("engineeringDays"))
    repository = sum(1 for node in nodes if node.get("repositoryMapping", {}).get("evidenceStatus") == "Mapped")
    traced = sum(1 for node in nodes if node.get("traceability", {}).get("requirementId") and node.get("traceability", {}).get("recommendationId"))
    criteria = sum(1 for node in stories if _strings(node.get("acceptanceCriteria")))
    coverage = round(criteria / max(1, len(stories)) * 100)
    estimate_score = round(estimated / max(1, len([node for node in nodes if node.get("type") not in {"Epic", "Feature"}])) * 100)
    repository_score = round(repository / total * 100)
    trace_score = round(traced / total * 100)
    overall = round(coverage * .3 + estimate_score * .2 + repository_score * .2 + trace_score * .3)
    risk = _text(proposal.get("estimate", {}).get("risk")) or "Medium"
    validation = {
        "status": "Passed" if mandatory_passed else "NeedsChanges",
        "mandatoryPassed": mandatory_passed,
        "findings": findings,
        "checkedAt": _now(),
    }
    health = {
        "overallHealth": overall,
        "coverage": coverage,
        "estimateCompleteness": estimate_score,
        "repositoryCoverage": repository_score,
        "requirementCoverage": trace_score,
        "engineeringConfidence": int(proposal.get("estimate", {}).get("confidence") or 0),
        "planningConfidence": int(_average([node.get("confidence") for node in nodes])),
        "risk": risk,
    }
    return validation, health


def _review_checklist(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    validation = proposal.get("validation") or {}
    health = proposal.get("health") or {}
    nodes = proposal.get("nodes") or []
    checks = [
        ("Requirement Coverage", health.get("requirementCoverage", 0) == 100, True),
        ("Acceptance Criteria", not any(item.get("code") == "missing_acceptance_criteria" for item in validation.get("findings") or []), True),
        ("Repository Mapping", health.get("repositoryCoverage", 0) > 0, False),
        ("Dependencies", not any(item.get("code") == "circular_dependency" for item in validation.get("findings") or []), True),
        ("Engineering Estimate", health.get("estimateCompleteness", 0) == 100, True),
        ("Story Points", all(node.get("storyPoints") for node in nodes if node.get("type") == "Story"), True),
        ("Implementation Order", len(proposal.get("implementationOrder") or []) == len(nodes), True),
        ("Risk", bool(proposal.get("estimate", {}).get("risk")), True),
        ("Architecture Review", True, False),
        ("Quality Score", health.get("overallHealth", 0) >= 70, True),
    ]
    return [{"name": name, "passed": bool(passed), "mandatory": mandatory} for name, passed, mandatory in checks]


def _finding(findings: list[dict[str, Any]], code: str, severity: str, node: dict[str, Any], message: str) -> None:
    findings.append({
        "findingId": "proposal-finding-" + _digest([code, node.get("nodeId"), message]),
        "code": code,
        "severity": severity,
        "nodeId": node.get("nodeId"),
        "title": node.get("title"),
        "message": message,
        "recommendation": _finding_recommendation(code),
    })


def _finding_recommendation(code: str) -> str:
    return {
        "duplicate_item": "Merge, rename, or delete the duplicate item.",
        "invalid_hierarchy": "Move the item under the required parent type.",
        "missing_acceptance_criteria": "Add measurable Acceptance Criteria before review.",
        "missing_estimate": "Regenerate or manually override the engineering estimate.",
        "missing_story_points": "Add Story Points before review.",
        "missing_repository": "Confirm a repository mapping or record that repository context is unavailable.",
        "missing_traceability": "Regenerate the item from its approved requirement boundary.",
        "circular_dependency": "Remove or redirect one dependency before review.",
    }.get(code, "Review and resolve this proposal finding.")


def _dependency_cycles(edges: list[dict[str, Any]], node_ids: set[str]) -> set[str]:
    graph = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if edge.get("from") in graph and edge.get("to") in graph:
            graph[edge["from"]].append(edge["to"])
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            cycles.update(visiting)
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for target in graph[node_id]:
            visit(target)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in graph:
        visit(node_id)
    return cycles


def _validate_parent(node: dict[str, Any], parent_id: str, nodes: list[dict[str, Any]]) -> None:
    expected = PARENT_TYPES.get(node["type"], "")
    if not expected:
        if parent_id:
            raise ValueError("Epic cannot have a proposal parent.")
        return
    parent = next((item for item in nodes if item["nodeId"] == parent_id), None)
    if not parent or parent["type"] != expected:
        raise ValueError(f"{node['type']} must be placed under a {expected}.")
    if node["nodeId"] == parent_id or parent_id in _descendants(node["nodeId"], nodes):
        raise ValueError("Move would create a circular hierarchy.")


def _descendants(node_id: str, nodes: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    queue = [node_id]
    while queue:
        parent = queue.pop()
        children = [node["nodeId"] for node in nodes if node.get("parentId") == parent and node["nodeId"] not in found]
        found.update(children)
        queue.extend(children)
    return found


def _nearest_parent(nodes: list[dict[str, Any]], kind: str) -> str:
    expected = PARENT_TYPES.get(kind, "")
    return next((node["nodeId"] for node in reversed(nodes) if node["type"] == expected), "")


def _history_entry(proposal: dict[str, Any], actor: str, reason: str, changes: list[str]) -> dict[str, Any]:
    return {
        "version": int(proposal.get("version") or 1),
        "author": actor,
        "reason": reason,
        "timestamp": _now(),
        "changes": changes,
        "snapshot": _snapshot(proposal),
    }


def _snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(proposal)
    snapshot.pop("history", None)
    return snapshot


def _for_recommendation(values: dict[str, Any], recommendation_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in values.values() if isinstance(item, dict) and item.get("recommendationId") == recommendation_id),
        None,
    )


def _node(proposal: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = next((item for item in proposal.get("nodes") or [] if item.get("nodeId") == node_id), None)
    if not node:
        raise LookupError(f"Planning Proposal node {node_id} was not found.")
    return node


def _type(value: Any) -> str:
    normalized = _text(value).casefold()
    if normalized in {"subtask", "sub task"}:
        return "Sub Task"
    return normalized.title()


def _required(value: dict[str, Any], key: str) -> str:
    result = _text(value.get(key))
    if not result:
        raise ValueError(f"{key} is required.")
    return result


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item.get("text") if isinstance(item, dict) else item) for item in value if _text(item.get("text") if isinstance(item, dict) else item)]
    return [_text(value)] if _text(value) else []


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _unique_dicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _average(values: list[Any]) -> float:
    numbers = [float(value or 0) for value in values]
    return sum(numbers) / max(1, len(numbers))


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
