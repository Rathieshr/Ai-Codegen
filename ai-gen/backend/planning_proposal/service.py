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
    "Mobile", "AI",
}
STORY_TYPES = {"New", "Enhancement", "Bug", "Refactor", "Spike", "Documentation"}
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
        reasoning_engine: Any | None = None,
        review_service: Any | None = None,
        ado_action_pack_preparer: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.recommendation_service = recommendation_service
        self.planning_context_service = planning_context_service
        self.requirement_planning_service = requirement_planning_service
        self.reasoning_engine = reasoning_engine or getattr(
            recommendation_service, "reasoning_engine", None
        )
        self.review_service = review_service
        self.ado_action_pack_preparer = ado_action_pack_preparer
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
        generated, generation_diagnostics = self._enrich_hierarchy(
            generated, context, recommendation, request,
        )
        version = int((existing or {}).get("version") or 0) + 1
        proposal = self._assemble(generated, context, recommendation, actor, version, existing)
        proposal["generationDiagnostics"] = generation_diagnostics
        values[proposal["proposalId"]] = proposal
        self.store.write(values)
        if existing and self.review_service:
            self.review_service.invalidate(proposal["proposalId"], proposal["version"], actor)
        self._publish("PlanningProposalGenerated", proposal)
        return proposal

    def _enrich_hierarchy(
        self,
        generated: dict[str, Any],
        context: dict[str, Any],
        recommendation: dict[str, Any],
        request: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Use Reasoning AI for item-specific planning, with one semantic repair pass."""
        baseline = deepcopy(generated)
        engineering_context = context.get("engineeringContext") or {}
        provider = _text(request.get("provider") or request.get("providerPreference")) or "Auto"
        available = getattr(self.reasoning_engine, "is_provider_available", None)
        if (
            not self.reasoning_engine
            or not engineering_context
            or (callable(available) and not available(provider))
        ):
            return baseline, {
                "reasoningMode": "Deterministic",
                "provider": "Deterministic",
                "model": "",
                "qualityRepairApplied": False,
                "qualityIssues": ["AI provider unavailable; evidence-safe planning fallback used."],
            }

        prompt_projection = _proposal_prompt_projection(
            baseline.get("planningProposal") or {}, context, recommendation,
        )
        result = self.reasoning_engine.analyze(
            "Planning Proposal",
            engineering_context,
            user_requirement=_proposal_requirement_text(context),
            provider=provider,
            correlation_id=_text(recommendation.get("correlationId")),
            options={"proposalSummary": prompt_projection},
        )
        candidate = _reasoned_work_items(result, context)
        issues = _reasoned_hierarchy_issues(candidate, context)
        repair_applied = False
        if issues and _text(result.get("reasoningMode")) == "AI":
            repaired = self.reasoning_engine.analyze(
                "Planning Proposal Quality Repair",
                engineering_context,
                user_requirement=_proposal_requirement_text(context),
                provider=provider,
                correlation_id=_text(recommendation.get("correlationId")),
                options={
                    "proposalSummary": {
                        **prompt_projection,
                        "weakCandidate": candidate,
                        "qualityIssues": issues,
                    },
                },
            )
            repaired_candidate = _reasoned_work_items(repaired, context)
            repaired_issues = _reasoned_hierarchy_issues(repaired_candidate, context)
            if len(repaired_issues) < len(issues):
                result, candidate, issues = repaired, repaired_candidate, repaired_issues
                repair_applied = True

        diagnostics = {
            "reasoningMode": _text(result.get("reasoningMode")) or "Deterministic",
            "provider": _text(result.get("provider")) or "Deterministic",
            "model": _text(result.get("model")),
            "promptVersion": _text(result.get("promptVersion")),
            "qualityRepairApplied": repair_applied,
            "qualityIssues": issues,
            "warnings": _strings(result.get("warnings")),
        }
        if issues:
            return baseline, diagnostics
        enriched = deepcopy(baseline)
        enriched["planningProposal"] = _legacy_proposal_from_reasoned_items(
            candidate, baseline.get("planningProposal") or {}, result,
        )
        return enriched, diagnostics

    def get(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.read().get(proposal_id)
        if not isinstance(proposal, dict):
            raise LookupError("Planning Proposal was not found.")
        return proposal

    def list(
        self,
        *,
        project_id: str = "",
        status: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        proposals = [
            deepcopy(value)
            for value in self.store.read().values()
            if isinstance(value, dict)
        ]
        if project_id:
            proposals = [
                value for value in proposals
                if _text(value.get("projectId")).casefold() == project_id.casefold()
            ]
        if status:
            proposals = [
                value for value in proposals
                if _text(value.get("status")).casefold() == status.casefold()
            ]
        proposals.sort(
            key=lambda value: _text(value.get("updatedAt") or value.get("createdAt")),
            reverse=True,
        )
        safe_limit = min(100, max(1, int(limit)))
        return {
            "proposals": proposals[:safe_limit],
            "count": len(proposals),
            "generatedAt": _now(),
        }

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
        elif action == "generate-next-stage":
            changes.extend(self._generate_next_stage(proposal))
        elif action in {"move", "delete", "duplicate", "merge", "split", "approve", "reject"}:
            changes.extend(self._node_operation(proposal, action, request))
        else:
            changes.extend(self._apply_edits(proposal, request))
        proposal.setdefault("userEdits", []).append({
            "actor": actor,
            "reason": reason,
            "changes": list(changes),
            "timestamp": _now(),
        })
        proposal = self._version(proposal, previous, actor, reason, changes)
        proposal = self._recalculate(proposal)
        values[proposal_id] = proposal
        self.store.write(values)
        self._publish("PlanningProposalUpdated", proposal)
        return proposal

    def _generate_next_stage(self, proposal: dict[str, Any]) -> list[str]:
        workflow = _planning_workflow(proposal)
        target = _text(workflow.get("generationTarget"))
        if not target:
            raise ValueError(_text(workflow.get("blockingReason")) or "The current planning stage is not ready to advance.")
        revealed = list((proposal.get("planningWorkflow") or {}).get("revealedTypes") or ["Epic", "Feature"])
        if target not in revealed:
            revealed.append(target)
        proposal["planningWorkflow"] = {"revealedTypes": revealed}
        return [f"Generated {target} drafts for approved parent items."]

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
        if self.review_service:
            raise ValueError(
                "Engineering Review is the mandatory approval gate. "
                "Complete the configured review chain before approving this Planning Proposal."
            )
        return self._finalize_approval(
            _required(request, "proposalId"),
            _required(request, "actor"),
            _text(request.get("comments")),
        )

    def _finalize_approval(
        self,
        proposal_id: str,
        actor: str,
        comments: str = "",
    ) -> dict[str, Any]:
        request = {"proposalId": proposal_id}
        proposal = self.validate(request)
        workflow = _planning_workflow(proposal)
        if not workflow.get("canApprove"):
            raise ValueError(
                _text(workflow.get("blockingReason"))
                or "Complete Feature, Story, and Task review before approving the Planning Proposal."
            )
        if not proposal.get("validation", {}).get("mandatoryPassed"):
            raise ValueError("Planning Proposal cannot be approved until mandatory validation findings are resolved.")
        if not self.review_service and proposal.get("review", {}).get("status") != "Completed":
            raise ValueError("Complete the Planning Proposal review checklist before approval.")
        proposal["status"] = "Approved"
        proposal["approvedBy"] = actor
        proposal["approvedAt"] = _now()
        proposal["review"] = {
            **dict(proposal.get("review") or {}),
            "status": "Completed",
            "reviewer": actor,
            "comments": comments,
            "reviewedAt": proposal["approvedAt"],
        }
        proposal["updatedAt"] = proposal["approvedAt"]
        for node in proposal.get("nodes") or []:
            if node.get("status") != "Rejected":
                node["status"] = "Approved"
        values = self.store.read()
        values[proposal["proposalId"]] = proposal
        self.store.write(values)
        self._publish("PlanningProposalApproved", proposal)
        if self.ado_action_pack_preparer:
            try:
                action_pack = self.ado_action_pack_preparer(proposal)
                proposal["azureDevOpsAutomation"] = {
                    "status": action_pack.get("approvalStatus") or "Prepared",
                    "packId": action_pack.get("packId"),
                    "operationCount": len(action_pack.get("proposedActions") or []),
                    "message": "Azure DevOps creation preview is ready in Approval Center.",
                }
            except Exception as error:
                proposal["azureDevOpsAutomation"] = {
                    "status": "NeedsConfiguration",
                    "packId": "",
                    "operationCount": 0,
                    "message": str(error),
                }
            proposal["updatedAt"] = _now()
            values = self.store.read()
            values[proposal["proposalId"]] = proposal
            self.store.write(values)
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

    def azure_devops_preview(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get(proposal_id)
        return {
            "proposalId": proposal_id,
            "proposalVersion": proposal["version"],
            "status": proposal["status"],
            "preview": deepcopy(proposal.get("azureDevOpsPreview") or {}),
            "notice": "Preview only. No Azure DevOps work item has been created or updated.",
        }

    def export(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get(proposal_id)
        return {
            "schemaVersion": "planning-proposal-v2",
            "exportedAt": _now(),
            "proposal": deepcopy(proposal),
            "notice": "Reviewable HEI artifact only. Azure DevOps synchronization is separate.",
        }

    def request_ai_review(self, request: dict[str, Any]) -> dict[str, Any]:
        proposal_id = _required(request, "proposalId")
        proposal, values = self._editable(proposal_id, request)
        context = self.planning_context_service.get(proposal["contextId"])
        engineering_context = context.get("engineeringContext") or {}
        if not self.reasoning_engine or not engineering_context:
            review = {
                "status": "Deterministic",
                "summary": "Proposal remains available for human review without an AI provider.",
                "recommendations": _validation_recommendations(
                    (proposal.get("validation") or {}).get("findings") or []
                ),
                "confidence": proposal.get("health", {}).get("overallHealth", 0),
                "reviewedAt": _now(),
            }
        else:
            result = self.reasoning_engine.analyze(
                "Planning Proposal Review",
                engineering_context,
                user_requirement=proposal.get("executiveSummary") or proposal["title"],
                provider=_text(request.get("provider")) or "Auto",
                correlation_id=proposal.get("correlationId") or "",
                options={
                    "proposalVersion": proposal["version"],
                    "proposalSummary": _review_projection(proposal),
                },
            )
            review = {
                "status": "Completed",
                "summary": _text(
                    (result.get("recommendation") or {}).get("action")
                    or (result.get("recommendation") or {}).get("title")
                ),
                "recommendations": _strings(result.get("reasoning")),
                "alternatives": list(result.get("alternatives") or []),
                "risks": _strings(result.get("risks")),
                "confidence": _confidence_value(result.get("confidence")),
                "reasoningMode": _text(result.get("reasoningMode")),
                "provider": _text(result.get("provider")),
                "promptVersion": _text(result.get("promptVersion")),
                "reviewedAt": _now(),
            }
        previous = _snapshot(proposal)
        proposal["aiReview"] = review
        proposal = self._version(
            proposal,
            previous,
            _text(request.get("actor")) or "HEI User",
            "Requested Planning Proposal AI review.",
            ["Recorded advisory Planning Proposal review."],
        )
        proposal = self._recalculate(proposal)
        values[proposal_id] = proposal
        self.store.write(values)
        self._publish("PlanningProposalAIReviewed", proposal)
        return proposal

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
        engineering_context = context.get("engineeringContext") or {}
        project_intelligence = engineering_context.get("projectIntelligence") or {}
        knowledge = project_intelligence.get("knowledge") or {}
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
        acceptance_catalog = _acceptance_catalog(requirement, nodes)
        definition_of_done = _definition_of_done(acceptance_catalog, nodes)
        dependency_graph = _dependency_graph(
            nodes, dependency_edges, engineering_context.get("dependencies") or {}
        )
        repository = engineering_context.get("repository") or context.get("repository") or {}
        business_goal = _first(_strings(requirement.get("businessGoals")))
        strategy = {
            "type": _text(recommendation.get("strategy")),
            "title": _text(recommendation.get("strategyTitle")),
            "summary": _text(recommendation.get("summary", {}).get("recommendation")),
            "reason": _text(recommendation.get("explanation", {}).get("whyThisApproach"))
            or _first(_strings(recommendation.get("engineeringReasoning"))),
            "confidence": int(recommendation.get("confidence", {}).get("overall") or 0),
        }
        executive_summary = _executive_summary(
            requirement, recommendation, nodes, estimate
        )
        engineering_notes = _engineering_notes(recommendation, engineering_context)
        risks = _proposal_risks(recommendation, requirement)
        azure_preview = _azure_devops_preview(
            proposal_id, nodes, context, recommendation
        )
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
            executiveSummary=executive_summary,
            businessGoal=business_goal,
            recommendedStrategy=strategy,
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
            acceptanceCriteria=acceptance_catalog,
            dependencyGraph=dependency_graph,
            engineeringNotes=engineering_notes,
            risks=risks,
            definitionOfDone=definition_of_done,
            azureDevOpsPreview=azure_preview,
            knowledgeVersion=_text(knowledge.get("version")),
            knowledgeReferences=_knowledge_references(knowledge),
            aiReview={},
            userEdits=[],
            author=actor,
            createdAt=_text((existing or {}).get("createdAt")) or now,
            updatedAt=now,
            history=[],
        ).to_dict()
        previous_history = list((existing or {}).get("history") or [])
        if existing:
            previous_history.append(_history_entry(existing, actor, "Entire proposal regenerated.", ["Regenerated proposal hierarchy."]))
        proposal["history"] = previous_history
        proposal["planningWorkflow"] = {
            "revealedTypes": list((existing or {}).get("planningWorkflow", {}).get("revealedTypes") or ["Epic", "Feature"]),
        }
        for node in proposal.get("nodes") or []:
            if node.get("type") == "Epic":
                node["status"] = "Approved"
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
        engineering_context = context.get("engineeringContext") or {}
        impact = recommendation.get("impact") or {}
        criteria = _strings(item.get("acceptanceCriteria"))
        if kind == "Story" and not criteria:
            criteria = _strings(requirement.get("acceptanceCriteria"))
        if kind in {"Epic", "Feature"}:
            criteria = _strings(item.get("successMeasures")) or criteria
            if not criteria:
                outcome = _text(item.get("businessValue") or change.get("reason"))
                if outcome:
                    criteria = [f"Success measure: {outcome.rstrip('.')}."]
        business_goals = _strings(requirement.get("businessGoals"))
        functional = _strings(requirement.get("functionalRequirements"))
        modules = _strings(item.get("repositoryModules")) or _strings(impact.get("affectedModules"))
        repository = engineering_context.get("repository") or context.get("repository") or {}
        knowledge = (
            (engineering_context.get("projectIntelligence") or {}).get("knowledge") or {}
        )
        criteria_details = _criteria_details(criteria, requirement)
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
            acceptanceCriterionIds=[
                _text(item.get("criterionId")) for item in criteria_details
                if _text(item.get("criterionId"))
            ],
            knowledgeReferences=_knowledge_references(knowledge),
            evidence=_node_evidence(change, repository, knowledge),
            contextVersion=_text(context.get("contextVersion")),
        )
        confidence = int(change.get("confidence") or recommendation.get("confidence", {}).get("overall") or 0)
        description = _text(item.get("description")) or _text(change.get("reason"))
        business_value = _text(item.get("businessValue")) or (
            business_goals[0] if business_goals else _text(impact.get("businessImpact"))
        )
        if _same_meaning(description, business_value):
            distinct_scope = _first(functional)
            description = distinct_scope if distinct_scope and not _same_meaning(distinct_scope, business_value) else (
                f"Define the approved {kind.lower()} scope for {title}."
            )
        return ProposalNode(
            nodeId=node_id,
            proposalId=proposal_id,
            parentId=parent_id,
            type=kind,
            title=title,
            description=description,
            businessValue=business_value,
            acceptanceCriteria=criteria,
            businessRules=_strings(requirement.get("businessRules")),
            dependencies=_strings(requirement.get("dependencies")),
            estimate={
                "engineeringDays": float(item.get("engineeringDays") or 0),
                "storyPoints": int(item.get("storyPoints") or 0) if kind == "Story" else 0,
                "confidence": confidence,
                "source": "Reasoning AI" if item.get("engineeringDays") or item.get("storyPoints") else "AI Estimate",
            },
            storyPoints=int(item.get("storyPoints") or 0) if kind == "Story" else 0,
            repositoryModules=modules,
            affectedApis=_strings(impact.get("affectedApis")),
            affectedScreens=_strings(impact.get("affectedScreens")),
            technicalNotes=_unique([
                *_strings(item.get("technicalNotes")),
                recommendation.get("expectedRepositoryImpact", ""),
                *recommendation.get("engineeringReasoning", []),
            ]),
            generatedTests=_suggested_tests(kind, criteria, impact),
            risk=_text(item.get("risk") or impact.get("riskLevel")) or "Medium",
            priority=_text(item.get("priority")) or ("High" if _text(impact.get("riskLevel")) in {"High", "Critical"} else "Medium"),
            origin="AI Suggested",
            confidence=confidence,
            reason=_text(change.get("reason")) or "Derived from the approved Planning Recommendation.",
            repositoryMapping={
                "repositoryId": _text(impact.get("repositoryId") or repository.get("repositoryId")),
                "repositoryName": _text(impact.get("repositoryName") or repository.get("repositoryName")),
                "snapshotVersion": _text(repository.get("repositorySnapshotVersion")),
                "mode": _text(repository.get("mode")),
                "modules": modules,
                "services": _strings(impact.get("affectedServices") or repository.get("services")),
                "apis": _strings(impact.get("affectedApis")),
                "screens": _strings(impact.get("affectedScreens")),
                "databaseObjects": _strings(
                    impact.get("affectedDatabaseObjects") or repository.get("databaseObjects")
                ),
                "externalIntegrations": _strings(impact.get("externalIntegrations")),
                "reason": _repository_mapping_reason(modules, impact, repository),
                "evidence": _repository_mapping_evidence(repository, modules),
                "evidenceStatus": "Mapped" if modules or repository.get("repositoryId") else "Missing",
            },
            traceability=traceability,
            planningVersion=version,
            status="Draft",
            taskType=_text(item.get("taskType")) if kind == "Task" else "",
            storyType=_story_type(kind, recommendation),
            order=order,
            acceptanceCriteriaDetails=criteria_details,
            affectedServices=_strings(impact.get("affectedServices") or repository.get("services")),
            affectedDatabaseObjects=_strings(
                impact.get("affectedDatabaseObjects") or repository.get("databaseObjects")
            ),
            externalIntegrations=_strings(impact.get("externalIntegrations")),
            evidence=_node_evidence(change, repository, knowledge),
            definitionOfDone=_node_definition_of_done(kind, criteria),
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
                    acceptanceCriteria=task["completionChecks"],
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
            if request.get("createNewVersion") is not True:
                raise ValueError("Approved, Published, or Archived proposals are immutable. Create a new version first.")
            proposal = deepcopy(proposal)
            proposal["status"] = "Draft"
            proposal["approvedBy"] = ""
            proposal["approvedAt"] = ""
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
                "generatedTests", "risk", "priority", "owner", "taskType", "storyType",
                "affectedServices", "affectedDatabaseObjects", "externalIntegrations",
                "definitionOfDone",
            ):
                if key in patch:
                    if key == "taskType" and patch[key] and patch[key] not in TASK_TYPES:
                        raise ValueError(f"taskType must be one of: {', '.join(sorted(TASK_TYPES))}.")
                    if key == "storyType" and patch[key] and patch[key] not in STORY_TYPES:
                        raise ValueError(f"storyType must be one of: {', '.join(sorted(STORY_TYPES))}.")
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
        for key in (
            "title", "executiveSummary", "businessGoal", "engineeringNotes",
            "risks", "definitionOfDone",
        ):
            if key in request:
                proposal[key] = deepcopy(request[key])
                changes.append(f"Updated Planning Proposal field {key}.")
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
                elif action == "approve" and item.get("parentId") == node["nodeId"] and item.get("status") == "Rejected":
                    item["status"] = "Draft"
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
        if self.review_service:
            self.review_service.invalidate(proposal["proposalId"], proposal["version"], actor)
        return proposal

    def _recalculate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        proposal["planningWorkflow"] = _planning_workflow(proposal)
        proposal["dependencies"] = _dependency_edges(proposal.get("nodes") or [])
        proposal["implementationOrder"] = _implementation_order(proposal.get("nodes") or [], proposal["dependencies"])
        proposal["acceptanceCriteria"] = _acceptance_catalog_from_nodes(
            proposal.get("nodes") or [], proposal.get("acceptanceCriteria") or []
        )
        proposal["definitionOfDone"] = _definition_of_done(
            proposal["acceptanceCriteria"], proposal.get("nodes") or [],
            existing=proposal.get("definitionOfDone") or [],
        )
        proposal["dependencyGraph"] = _dependency_graph(
            proposal.get("nodes") or [],
            proposal["dependencies"],
            (proposal.get("dependencyGraph") or {}).get("sourceDependencies") or {},
        )
        proposal["azureDevOpsPreview"] = _azure_devops_preview_from_record(proposal)
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


def _acceptance_catalog(
    requirement: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = [
        dict(item) for item in requirement.get("acceptanceCriteriaRecords") or []
        if isinstance(item, dict) and _text(item.get("text"))
    ]
    if not records:
        origin = _text(
            (requirement.get("acceptanceCriteriaState") or {}).get("origin")
            or (requirement.get("fieldOrigins") or {}).get("acceptanceCriteria")
        ) or "Source"
        records = [
            {
                "criterionId": "ac-" + _digest([text, index]),
                "title": f"Acceptance Criterion {index + 1}",
                "text": text,
                "origin": origin,
                "status": "Approved",
                "confidence": 1.0 if origin in {"Source", "Source Derived", "Imported"} else 0.8,
                "evidence": [],
                "quality": {"traceable": bool(origin)},
                "order": index + 1,
            }
            for index, text in enumerate(_strings(requirement.get("acceptanceCriteria")))
        ]
    return _acceptance_catalog_from_nodes(nodes, records)


def _acceptance_catalog_from_nodes(
    nodes: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for item in existing:
        if not isinstance(item, dict) or not _text(item.get("text")):
            continue
        key = _text(item.get("criterionId")) or _text(item.get("text")).casefold()
        catalog[key] = {**deepcopy(item), "mappedNodeIds": []}
    for node in nodes:
        if node.get("status") == "Rejected":
            continue
        if node.get("type") != "Story" or node.get("status") == "Rejected":
            continue
        details = list(node.get("acceptanceCriteriaDetails") or [])
        for index, text in enumerate(_strings(node.get("acceptanceCriteria"))):
            detail = next((
                item for item in details
                if _text(item.get("text")).casefold() == text.casefold()
            ), {})
            key = _text(detail.get("criterionId")) or text.casefold()
            if key not in catalog:
                catalog[key] = {
                    "criterionId": _text(detail.get("criterionId")) or "ac-" + _digest([text]),
                    "title": _text(detail.get("title")) or f"Acceptance Criterion {index + 1}",
                    "text": text,
                    "origin": _text(detail.get("origin")) or node.get("origin") or "AI Suggested",
                    "status": _text(detail.get("status")) or "Approved",
                    "confidence": detail.get("confidence", node.get("confidence", 0) / 100),
                    "evidence": list(detail.get("evidence") or []),
                    "quality": dict(detail.get("quality") or {}),
                    "order": detail.get("order", index + 1),
                    "mappedNodeIds": [],
                }
            catalog[key].setdefault("mappedNodeIds", []).append(node["nodeId"])
    output = list(catalog.values())
    for item in output:
        item["mappedNodeIds"] = _unique(_strings(item.get("mappedNodeIds")))
    return sorted(output, key=lambda item: (int(item.get("order") or 0), _text(item.get("text"))))


def _criteria_details(
    criteria: list[str],
    requirement: dict[str, Any],
) -> list[dict[str, Any]]:
    records = [
        dict(item) for item in requirement.get("acceptanceCriteriaRecords") or []
        if isinstance(item, dict)
    ]
    by_text = {
        _text(item.get("text")).casefold(): item
        for item in records if _text(item.get("text"))
    }
    origin = _text(
        (requirement.get("acceptanceCriteriaState") or {}).get("origin")
        or (requirement.get("fieldOrigins") or {}).get("acceptanceCriteria")
    ) or "Source"
    return [
        deepcopy(by_text.get(text.casefold()) or {
            "criterionId": "ac-" + _digest([text]),
            "title": f"Acceptance Criterion {index + 1}",
            "text": text,
            "origin": origin,
            "status": "Approved",
            "confidence": 1.0 if origin in {"Source", "Source Derived", "Imported"} else 0.8,
            "evidence": [],
            "quality": {"traceable": bool(origin)},
            "order": index + 1,
        })
        for index, text in enumerate(criteria)
    ]


def _definition_of_done(
    acceptance: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    *,
    existing: list[str] | None = None,
) -> list[str]:
    return _unique([
        *(existing or []),
        "Every mapped Acceptance Criterion is implemented and verified.",
        "Required functional, negative, permission, integration, and regression tests pass.",
        "Repository and architecture mappings are reviewed against current evidence.",
        "No unresolved mandatory Planning Proposal validation findings remain.",
        "Dependencies, risks, deployment impact, and rollback expectations are documented.",
        *(
            ["All approved Acceptance Criteria retain source and evidence traceability."]
            if acceptance else []
        ),
        *(
            ["Every Story has at least one implementation Task."]
            if any(node.get("type") == "Story" for node in nodes) else []
        ),
    ])


def _node_definition_of_done(kind: str, criteria: list[str]) -> list[str]:
    if kind == "Story":
        return _unique([
            "All Story Acceptance Criteria are verified.",
            "Mapped implementation tasks and required tests are complete.",
        ])
    if kind in {"Task", "Sub Task"}:
        return [
            "Implementation is complete within the mapped repository boundary.",
            "Relevant tests pass and no unrelated modules are changed.",
        ]
    return ["All approved child artifacts satisfy their validation and traceability gates."]


def _dependency_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    source_dependencies: dict[str, Any],
) -> dict[str, Any]:
    by_id = {node["nodeId"]: node for node in nodes}
    categorized: dict[str, list[dict[str, Any]]] = {
        "storyDependencies": [],
        "featureDependencies": [],
        "repositoryDependencies": list(source_dependencies.get("repositoryDependencies") or []),
        "crossTeamDependencies": [],
        "technicalDependencies": [],
    }
    for edge in edges:
        source = by_id.get(edge.get("from")) or {}
        target = by_id.get(edge.get("to")) or {}
        value = {
            **edge,
            "fromTitle": source.get("title"),
            "toTitle": target.get("title"),
        }
        if source.get("type") == "Story" and target.get("type") == "Story":
            categorized["storyDependencies"].append(value)
        elif source.get("type") == "Feature" or target.get("type") == "Feature":
            categorized["featureDependencies"].append(value)
        else:
            categorized["technicalDependencies"].append(value)
    categorized["technicalDependencies"].extend(
        list(source_dependencies.get("moduleDependencies") or [])
        + list(source_dependencies.get("apiDependencies") or [])
        + list(source_dependencies.get("architectureDependencies") or [])
    )
    return {
        "nodes": [
            {"id": node["nodeId"], "type": node["type"], "title": node["title"]}
            for node in nodes if node.get("status") != "Rejected"
        ],
        "edges": edges,
        "implementationOrder": _implementation_order(nodes, edges),
        "categories": categorized,
        "sourceDependencies": deepcopy(source_dependencies),
    }


def _executive_summary(
    requirement: dict[str, Any],
    recommendation: dict[str, Any],
    nodes: list[dict[str, Any]],
    estimate: dict[str, Any],
) -> str:
    counts = {
        kind: sum(1 for node in nodes if node.get("type") == kind)
        for kind in ("Epic", "Feature", "Story", "Task")
    }
    strategy = _text(recommendation.get("strategy")).replace("_", " ").title()
    goal = _first(_strings(requirement.get("businessGoals"))) or _text(
        requirement.get("planningRequirement")
    )
    return (
        f"{strategy or 'Approved planning strategy'} for {goal}. "
        f"The proposal contains {counts['Epic']} Epic, {counts['Feature']} Feature(s), "
        f"{counts['Story']} Story/Stories, and {counts['Task']} Task(s), estimated at "
        f"{estimate['engineeringDays']} engineering day(s) and {estimate['storyPoints']} Story Points."
    )


def _engineering_notes(
    recommendation: dict[str, Any],
    engineering_context: dict[str, Any],
) -> list[str]:
    architecture = engineering_context.get("architecture") or {}
    repository = engineering_context.get("repository") or {}
    return _unique([
        *_strings(recommendation.get("engineeringReasoning")),
        _text(recommendation.get("expectedRepositoryImpact")),
        *[
            f"Architecture layer: {item}"
            for item in _strings(architecture.get("layers"))
        ],
        *[
            f"Repository warning: {item}"
            for item in _strings(repository.get("warnings"))
        ],
    ])


def _proposal_risks(
    recommendation: dict[str, Any],
    requirement: dict[str, Any],
) -> list[dict[str, Any]]:
    values = _unique([
        *_strings(requirement.get("risks")),
        *_strings((recommendation.get("impact") or {}).get("risks")),
        *_strings((recommendation.get("impact") or {}).get("potentialRisks")),
        *_strings(recommendation.get("risks")),
    ])
    level = _text((recommendation.get("impact") or {}).get("riskLevel")) or "Medium"
    return [
        {
            "riskId": "proposal-risk-" + _digest([value]),
            "description": value,
            "level": level,
            "mitigation": "Review during proposal validation and map to an owning Story or Task.",
            "source": "Approved Planning Recommendation",
        }
        for value in values
    ]


def _knowledge_references(knowledge: dict[str, Any]) -> list[str]:
    return _unique([
        *[f"Module:{item}" for item in _strings(knowledge.get("modules"))],
        *[f"Flow:{item}" for item in _strings(knowledge.get("flows"))],
        *[f"Standard:{item}" for item in _strings(knowledge.get("standards"))],
        *[f"Document:{_text(item.get('path'))}" for item in knowledge.get("sourceFiles") or [] if isinstance(item, dict)],
    ])


def _node_evidence(
    change: dict[str, Any],
    repository: dict[str, Any],
    knowledge: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence = []
    for item in change.get("evidence") or []:
        evidence.append(item if isinstance(item, dict) else {
            "type": "PlanningRecommendation", "value": _text(item),
            "source": "Approved Planning Recommendation",
        })
    if repository.get("repositorySnapshotVersion"):
        evidence.append({
            "type": "RepositorySnapshot",
            "value": _text(repository.get("repositorySnapshotVersion")),
            "source": "Repository Intelligence",
        })
    if knowledge.get("version"):
        evidence.append({
            "type": "KnowledgeVersion",
            "value": _text(knowledge.get("version")),
            "source": "Knowledge Registry",
        })
    return _unique_dicts(evidence)


def _repository_mapping_reason(
    modules: list[str],
    impact: dict[str, Any],
    repository: dict[str, Any],
) -> str:
    if modules:
        return "Affected modules were selected by Engineering Intelligence for the approved requirement intent."
    if repository.get("repositoryId"):
        return "Repository is selected, but module-level evidence requires review."
    return "Repository Intelligence is unavailable; no repository mapping was invented."


def _repository_mapping_evidence(
    repository: dict[str, Any],
    modules: list[str],
) -> list[dict[str, Any]]:
    evidence = []
    if repository.get("repositorySnapshotVersion"):
        evidence.append({
            "type": "RepositorySnapshot",
            "value": _text(repository.get("repositorySnapshotVersion")),
            "source": "Repository Intelligence",
        })
    evidence.extend({
        "type": "Module",
        "value": module,
        "source": "Engineering Intelligence",
    } for module in modules)
    return evidence


def _story_type(kind: str, recommendation: dict[str, Any]) -> str:
    if kind != "Story":
        return ""
    strategy = _text(recommendation.get("strategy")).upper()
    if "BUG" in strategy:
        return "Bug"
    if "REFACTOR" in strategy or "TECHNICAL_DEBT" in strategy:
        return "Refactor"
    if "SPIKE" in strategy:
        return "Spike"
    if "DOCUMENTATION" in strategy:
        return "Documentation"
    if "EXTEND" in strategy or "ENHANCEMENT" in strategy or "MODIFY" in strategy:
        return "Enhancement"
    return "New"


def _azure_devops_preview(
    proposal_id: str,
    nodes: list[dict[str, Any]],
    context: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    ado = context.get("azureDevOps") or {}
    return _build_ado_preview(
        proposal_id,
        nodes,
        area_path=_text(ado.get("currentAreaPath")),
        iteration_path=_text(
            (ado.get("currentIteration") or {}).get("path")
            or (ado.get("currentIteration") or {}).get("name")
        ),
        project_id=_text(context.get("projectId") or recommendation.get("projectId")),
    )


def _planning_workflow(proposal: dict[str, Any]) -> dict[str, Any]:
    """Derive the persisted, single-screen planning lifecycle from artifact state."""
    order = ["Epic", "Feature", "Story", "Task"]
    labels = {"Epic": "Epic", "Feature": "Features", "Story": "Stories", "Task": "Tasks"}
    stored = (proposal.get("planningWorkflow") or {}).get("revealedTypes") or ["Epic", "Feature"]
    revealed = [kind for kind in order if kind in stored]
    if "Epic" not in revealed:
        revealed.insert(0, "Epic")
    if "Feature" not in revealed:
        revealed.append("Feature")
    proposal_view = {**proposal, "planningWorkflow": {"revealedTypes": revealed}}
    visible = _visible_workflow_nodes(proposal_view)
    deepest = max((kind for kind in revealed if any(node.get("type") == kind for node in visible)), key=order.index, default="Epic")
    review_items = [node for node in visible if node.get("type") == deepest and node.get("status") != "Rejected"]
    pending = [node for node in review_items if node.get("status") not in {"Approved", "Rejected"}]
    approved = [node for node in review_items if node.get("status") == "Approved"]
    next_kind = order[order.index(deepest) + 1] if deepest != "Task" else ""
    generation_target = ""
    blocking_reason = ""
    if pending:
        next_action = f"Review {len(pending)} Remaining {labels[deepest]}"
        blocking_reason = f"{len(pending)} {labels[deepest].lower()} still require approval or rejection."
    elif deepest == "Task":
        next_action = "Review & Approve Planning Proposal"
    elif approved:
        generation_target = next_kind
        next_action = f"Generate {labels[next_kind]}"
    else:
        next_action = f"Review {labels[deepest]}"
        blocking_reason = f"Approve at least one {deepest.lower()} before generating {labels[next_kind]}."

    stages = []
    for kind in order:
        if kind == "Epic":
            state = "Done"
        elif kind not in revealed:
            state = "Locked"
        elif kind == deepest and pending:
            state = "Active"
        elif kind == deepest and not pending:
            state = "Done"
        else:
            items = [node for node in visible if node.get("type") == kind and node.get("status") != "Rejected"]
            state = "Done" if items and all(node.get("status") == "Approved" for node in items) else "Active"
        stages.append({"type": kind, "label": f"{labels[kind]} Review" if kind != "Epic" else "Epic", "state": state})

    return {
        "revealedTypes": revealed,
        "currentType": deepest,
        "nextAction": next_action,
        "blockingReason": blocking_reason,
        "generationTarget": generation_target,
        "pendingCount": len(pending),
        "approvedCount": len(approved),
        "visibleNodeIds": [node["nodeId"] for node in visible],
        "canApprove": deepest == "Task" and not pending and bool(approved),
        "stages": stages,
    }


def _visible_workflow_nodes(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = list(proposal.get("nodes") or [])
    revealed = set((proposal.get("planningWorkflow") or {}).get("revealedTypes") or ["Epic", "Feature"])
    by_id = {node.get("nodeId"): node for node in nodes}
    visible: list[dict[str, Any]] = []
    for node in nodes:
        kind = node.get("type")
        if kind not in revealed:
            continue
        parent_id = node.get("parentId")
        if kind in {"Story", "Task", "Sub Task"}:
            parent = by_id.get(parent_id)
            if not parent or parent.get("status") != "Approved":
                continue
        visible.append(node)
    return visible


def _azure_devops_preview_from_record(proposal: dict[str, Any]) -> dict[str, Any]:
    existing = proposal.get("azureDevOpsPreview") or {}
    return _build_ado_preview(
        proposal["proposalId"],
        _visible_workflow_nodes(proposal),
        area_path=_text(existing.get("areaPath")),
        iteration_path=_text(existing.get("iterationPath")),
        project_id=_text(existing.get("projectId") or proposal.get("projectId")),
    )


def _build_ado_preview(
    proposal_id: str,
    nodes: list[dict[str, Any]],
    *,
    area_path: str,
    iteration_path: str,
    project_id: str,
) -> dict[str, Any]:
    active = [node for node in nodes if node.get("status") != "Rejected"]
    return {
        "previewId": "ado-preview-" + _digest([proposal_id, [(item["nodeId"], item["title"]) for item in active]]),
        "projectId": project_id,
        "areaPath": area_path,
        "iterationPath": iteration_path,
        "tags": ["HEI", "Planning Proposal"],
        "workItems": [
            {
                "proposalNodeId": node["nodeId"],
                "workItemType": "User Story" if node["type"] == "Story" else node["type"],
                "title": node["title"],
                "description": node["description"],
                "parentProposalNodeId": node["parentId"],
                "storyPoints": node["storyPoints"] if node["type"] == "Story" else None,
                "acceptanceCriteria": node["acceptanceCriteria"],
                "operation": "Create" if node.get("origin") == "AI Suggested" else "Modify",
            }
            for node in active
        ],
        "links": [
            {
                "type": "ParentChild",
                "parentProposalNodeId": node["parentId"],
                "childProposalNodeId": node["nodeId"],
            }
            for node in active if node.get("parentId")
        ],
        "summary": {
            kind: sum(1 for node in active if node["type"] == kind)
            for kind in NODE_TYPES
        },
        "writeStatus": "PreviewOnly",
        "writesPerformed": 0,
        "requiresApprovedProposal": True,
    }


def _review_projection(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposalId": proposal["proposalId"],
        "version": proposal["version"],
        "strategy": proposal.get("recommendedStrategy") or {},
        "nodeCounts": {
            kind: sum(1 for node in proposal.get("nodes") or [] if node.get("type") == kind)
            for kind in NODE_TYPES
        },
        "validation": proposal.get("validation") or {},
        "health": proposal.get("health") or {},
        "risks": proposal.get("risks") or [],
    }


def _validation_recommendations(findings: list[dict[str, Any]]) -> list[str]:
    return _unique([
        _text(item.get("recommendation")) or _finding_recommendation(_text(item.get("code")))
        for item in findings
    ]) or ["Complete the human review checklist before approval."]


def _proposal_requirement_text(context: dict[str, Any]) -> str:
    requirement = context.get("requirement") or {}
    return _text(
        requirement.get("planningRequirement")
        or requirement.get("normalizedRequirement")
        or requirement.get("title")
    )


def _proposal_prompt_projection(
    baseline: dict[str, Any],
    context: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    requirement = context.get("requirement") or {}
    criteria = _strings(requirement.get("acceptanceCriteria"))
    return {
        "approvedStrategy": recommendation.get("strategy"),
        "approvedAcceptanceCriteria": [
            {"id": f"AC-{index}", "text": value}
            for index, value in enumerate(criteria, start=1)
        ],
        "baselineHierarchy": {
            "changes": list(baseline.get("changes") or []),
            "items": list(baseline.get("items") or []),
        },
        "qualityRules": [
            "Descriptions and business values must be specific to each item.",
            "Epic and Feature require distinct, measurable successMeasures that describe their own outcome.",
            "Only Stories use approved Acceptance Criteria identifiers and Story Points.",
            "Tasks require distinct engineering scope, completion checks, task type, and engineering days.",
            "Epic and Feature must not repeat Story Acceptance Criteria.",
        ],
    }


def _reasoned_work_items(
    result: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendation = result.get("recommendation") or {}
    hierarchy = recommendation.get("hierarchy") or {}
    raw_items = hierarchy.get("workItems") or recommendation.get("workItems") or []
    requirement = context.get("requirement") or {}
    approved = _strings(requirement.get("acceptanceCriteria"))
    criteria_by_id = {f"AC-{index}": value for index, value in enumerate(approved, start=1)}
    criteria_by_text = {value.casefold(): value for value in approved}
    repository = (context.get("engineeringContext") or {}).get("repository") or {}
    allowed_modules = _unique(_strings(repository.get("modules") or repository.get("affectedModules")))
    allowed_by_name = {value.casefold(): value for value in allowed_modules}
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items if isinstance(raw_items, list) else []):
        if not isinstance(raw, dict):
            continue
        kind = _type(raw.get("type"))
        if kind not in {"Epic", "Feature", "Story", "Task"}:
            continue
        criterion_ids = _strings(raw.get("acceptanceCriteriaIds"))
        criteria = [criteria_by_id[value] for value in criterion_ids if value in criteria_by_id]
        for value in _strings(raw.get("acceptanceCriteria")):
            approved_value = criteria_by_text.get(value.casefold())
            if approved_value:
                criteria.append(approved_value)
        criteria = _unique(criteria) if kind == "Story" else []
        success_measures = _unique(_strings(raw.get("successMeasures"))) if kind in {"Epic", "Feature"} else []
        checks = _unique(_strings(raw.get("completionChecks")))
        modules = [
            allowed_by_name[value.casefold()]
            for value in _strings(raw.get("repositoryModules"))
            if value.casefold() in allowed_by_name
        ]
        story_points = int(raw.get("storyPoints") or 0) if kind == "Story" else 0
        output.append({
            "key": _text(raw.get("key")) or f"item-{index + 1}",
            "parentKey": _text(raw.get("parentKey")),
            "type": kind,
            "title": _text(raw.get("title")),
            "description": _text(raw.get("description")),
            "businessValue": _text(raw.get("businessValue")),
            "acceptanceCriteria": criteria,
            "successMeasures": success_measures,
            "completionChecks": checks,
            "storyPoints": story_points,
            "engineeringDays": round(float(raw.get("engineeringDays") or 0), 2),
            "taskType": _text(raw.get("taskType")),
            "repositoryModules": _unique(modules),
            "technicalNotes": _unique(_strings(raw.get("technicalNotes"))),
            "risk": _text(raw.get("risk")) or "Medium",
            "priority": _text(raw.get("priority")) or "Medium",
        })
    return output


def _reasoned_hierarchy_issues(
    items: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    by_key = {item["key"]: item for item in items}
    counts = {kind: sum(1 for item in items if item["type"] == kind) for kind in ("Epic", "Feature", "Story", "Task")}
    if counts["Epic"] != 1:
        issues.append("Return exactly one Epic.")
    for kind in ("Feature", "Story", "Task"):
        if not counts[kind]:
            issues.append(f"Return at least one {kind}.")
    if len(by_key) != len(items):
        issues.append("Every work item key must be unique.")
    title_keys: set[tuple[str, str, str]] = set()
    descriptions: dict[str, list[str]] = {}
    expected_parent = {"Feature": "Epic", "Story": "Feature", "Task": "Story"}
    for item in items:
        label = f"{item['type']} {item['title'] or item['key']}"
        if not item["title"]:
            issues.append(f"{label} requires a title.")
        if len(item["description"].split()) < 6:
            issues.append(f"{label} requires an item-specific description.")
        if not item["businessValue"]:
            issues.append(f"{label} requires item-specific business value.")
        parent_type = expected_parent.get(item["type"])
        if parent_type:
            parent = by_key.get(item["parentKey"])
            if not parent or parent["type"] != parent_type:
                issues.append(f"{label} requires a {parent_type} parentKey.")
        normalized_title = _text(item["title"]).casefold()
        title_key = (item["type"], item["parentKey"], normalized_title)
        if title_key in title_keys:
            issues.append(f"Duplicate {label} title.")
        title_keys.add(title_key)
        normalized_description = " ".join(item["description"].casefold().split())
        if normalized_description:
            descriptions.setdefault(normalized_description, []).append(label)
        if item["type"] == "Story":
            if not item["acceptanceCriteria"]:
                issues.append(f"{label} must map at least one approved Acceptance Criterion.")
            if item["storyPoints"] not in {1, 2, 3, 5, 8, 13}:
                issues.append(f"{label} Story Points must be 1, 2, 3, 5, 8, or 13.")
        if item["type"] in {"Epic", "Feature"} and not item["successMeasures"]:
            issues.append(f"{label} requires item-specific successMeasures.")
        if item["type"] == "Task":
            if not item["completionChecks"]:
                issues.append(f"{label} requires task-specific completion checks.")
            if item["engineeringDays"] <= 0:
                issues.append(f"{label} requires a positive engineeringDays estimate.")
            if item["taskType"] not in TASK_TYPES:
                issues.append(f"{label} requires a supported taskType.")
    for labels in descriptions.values():
        if len(labels) > 1:
            issues.append("Cloned description detected across: " + ", ".join(labels) + ".")
    approved_count = len(_strings((context.get("requirement") or {}).get("acceptanceCriteria")))
    if approved_count and not any(item["acceptanceCriteria"] for item in items if item["type"] == "Story"):
        issues.append("Map approved Acceptance Criteria to Stories by AC identifier.")
    return _unique(issues)


def _legacy_proposal_from_reasoned_items(
    items: list[dict[str, Any]],
    baseline: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    by_key = {item["key"]: item for item in items}
    confidence = _confidence_value(result.get("confidence"))
    changes: list[dict[str, Any]] = []
    legacy_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        parent = by_key.get(item["parentKey"]) or {}
        reason = f"Item-specific {item['type']} scope generated from the approved Planning Recommendation."
        changes.append({
            "changeId": "change-" + _digest([item["key"], item["type"], item["title"]]),
            "action": "Create",
            "artifactType": item["type"],
            "title": item["title"],
            "parentTitle": parent.get("title", ""),
            "confidence": confidence,
            "reason": reason,
            "selected": True,
        })
        legacy_items.append({
            "alias": item["key"],
            "parentAlias": item["parentKey"],
            "type": item["type"],
            "title": item["title"],
            "description": item["description"],
            "businessValue": item["businessValue"],
            "acceptanceCriteria": item["acceptanceCriteria"] if item["type"] == "Story" else item["completionChecks"] if item["type"] == "Task" else item["successMeasures"],
            "successMeasures": item["successMeasures"],
            "storyPoints": item["storyPoints"],
            "engineeringDays": item["engineeringDays"],
            "taskType": item["taskType"],
            "repositoryModules": item["repositoryModules"],
            "technicalNotes": item["technicalNotes"],
            "risk": item["risk"],
            "priority": item["priority"],
        })
    return {
        **deepcopy(baseline),
        "schemaVersion": "hei-planning-proposal-ai-v1",
        "changes": changes,
        "items": legacy_items,
        "confidence": confidence,
        "reasoning": _strings(result.get("reasoning")),
        "provider": _text(result.get("provider")),
        "model": _text(result.get("model")),
        "promptVersion": _text(result.get("promptVersion")),
    }


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
    supplied_days = sum(float(node.get("estimate", {}).get("engineeringDays") or 0) for node in work)
    missing_days = [node for node in work if not node.get("estimate", {}).get("engineeringDays")]
    remaining_days = max(0.0, float(estimate["engineeringDays"]) - supplied_days)
    per_days = round(remaining_days / len(missing_days), 2) if missing_days else 0
    stories = [node for node in work if node["type"] == "Story"]
    supplied_points = sum(int(node.get("storyPoints") or 0) for node in stories)
    missing_points = [node for node in stories if not node.get("storyPoints")]
    remaining_points = max(0, int(estimate["storyPoints"]) - supplied_points)
    per_points = max(1, round(remaining_points / len(missing_points))) if missing_points and remaining_points else 0
    for node in work:
        days = float(node.get("estimate", {}).get("engineeringDays") or per_days)
        points = int(node.get("storyPoints") or per_points) if node["type"] == "Story" else 0
        node["estimate"] = {
            "engineeringDays": days,
            "storyPoints": points,
            "confidence": estimate["confidence"],
            "source": node.get("estimate", {}).get("source") or "AI Estimate",
        }
        node["storyPoints"] = points


def _task_blueprints(story: dict[str, Any], recommendation: dict[str, Any]) -> list[dict[str, Any]]:
    blueprints = []
    scope = _task_scope(story.get("title"))
    if story.get("affectedScreens"):
        blueprints.append(("Frontend", f"Build {scope} user experience", "Implement the approved interaction states and screen behavior.", ["The approved user states render and respond as described by the Story."]))
    if story.get("affectedApis"):
        blueprints.append(("API", f"Add {scope} API behavior", "Implement bounded API behavior and validation for the mapped Acceptance Criteria.", ["The mapped API behavior returns the expected result and validates invalid input."]))
    if story.get("repositoryModules"):
        blueprints.append(("Backend", f"Implement {scope} domain behavior", "Implement the approved behavior in evidence-matched repository modules.", ["The domain behavior satisfies the mapped Story outcome within approved modules."]))
    if not any(item[0] in {"Frontend", "API", "Backend"} for item in blueprints):
        blueprints.append((
            "Repository",
            f"Locate {scope} implementation boundary",
            "Identify the closest existing implementation and confirm the files and modules allowed for this Story.",
            ["The implementation boundary and affected existing files are documented without inventing paths."],
        ))
        blueprints.append((
            "Repository",
            f"Implement {scope} in the confirmed boundary",
            "Implement only the approved Story behavior after the repository boundary is confirmed.",
            ["The approved behavior is implemented only inside the confirmed repository boundary."],
        ))
    blueprints.append((
        "Testing",
        f"Verify {scope} acceptance scenarios",
        "Add focused tests mapped to the Story Acceptance Criteria and affected engineering areas.",
        ["Each mapped Story criterion has a focused passing test and relevant negative coverage."],
    ))
    return [
        {
            "type": kind,
            "title": title,
            "description": description,
            "completionChecks": checks,
            "tests": _suggested_tests("Task", story.get("acceptanceCriteria") or [], recommendation.get("impact") or {}),
        }
        for kind, title, description, checks in blueprints
    ]


def _task_scope(value: Any) -> str:
    words = _text(value).split()
    while words and words[0].casefold() in {
        "add", "allow", "create", "deliver", "enable", "implement", "provide", "support",
    }:
        words.pop(0)
    scope = " ".join(words[:9]).strip()
    return scope or "approved Story"


def _looks_like_acceptance_criterion_title(value: Any) -> bool:
    title = _text(value).casefold()
    return title.startswith(("given ", "when ", "then ", "scenario:")) or (
        " given " in f" {title} " and " when " in f" {title} " and " then " in f" {title} "
    )


def _same_meaning(left: Any, right: Any) -> bool:
    left_text = _text(left).casefold()
    right_text = _text(right).casefold()
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    left_words = {word for word in left_text.replace(".", " ").replace(",", " ").split() if len(word) > 2}
    right_words = {word for word in right_text.replace(".", " ").replace(",", " ").split() if len(word) > 2}
    return bool(left_words and right_words) and len(left_words & right_words) / len(left_words | right_words) >= .9


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
    active = [node for node in nodes if node.get("status") != "Rejected"]
    executable = [node for node in active if node.get("type") in {"Task", "Sub Task"}]
    if not executable:
        executable = [node for node in active if node.get("type") == "Story"]
    executable_ids = {node["nodeId"] for node in executable}
    dependencies = {node["nodeId"]: set() for node in executable}
    for edge in edges:
        if edge["from"] in executable_ids and edge["to"] in executable_ids:
            dependencies.setdefault(edge["from"], set()).add(edge["to"])
    ordered: list[str] = []
    remaining = set(dependencies)
    while remaining:
        ready = sorted(
            [node_id for node_id in remaining if not (dependencies[node_id] & remaining)],
            key=lambda node_id: next((int(node.get("order") or 0) for node in executable if node["nodeId"] == node_id), 0),
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
        if node.get("type") == "Story" and _looks_like_acceptance_criterion_title(node.get("title")):
            _finding(
                findings, "acceptance_criterion_used_as_story", "Error", node,
                "Story title is an Acceptance Criterion. Group the criterion under an outcome-oriented Story.",
            )
        if _same_meaning(node.get("description"), node.get("businessValue")):
            _finding(
                findings, "duplicate_business_context", "Warning", node,
                "Description and Business Value repeat the same content and require distinct wording.",
            )
        if node.get("type") == "Story" and not any(
            item.get("type") == "Task" and item.get("parentId") == node.get("nodeId")
            and item.get("status") != "Rejected"
            for item in nodes
        ):
            _finding(findings, "orphan_story", "Error", node, "Story requires at least one implementation Task.")
        if node.get("type") == "Story" and any(
            _text(item.get("status")).casefold() not in {"approved", "sourceprovided"}
            for item in node.get("acceptanceCriteriaDetails") or []
        ):
            _finding(
                findings, "unapproved_acceptance_criteria", "Error", node,
                "AI-suggested Acceptance Criteria must be approved, edited, or discarded before proposal approval.",
            )
        if node.get("type") in {"Story", "Task", "Sub Task"} and not node.get("estimate", {}).get("engineeringDays"):
            _finding(findings, "missing_estimate", "Error", node, "Engineering estimate is required.")
        if node.get("type") == "Story" and not node.get("storyPoints"):
            _finding(findings, "missing_story_points", "Error", node, "Story Points are required.")
        if node.get("repositoryMapping", {}).get("evidenceStatus") == "Missing":
            _finding(findings, "missing_repository", "Warning", node, "Repository mapping requires review.")
        elif not node.get("repositoryMapping", {}).get("reason"):
            _finding(findings, "weak_repository_mapping", "Warning", node, "Repository mapping requires an evidence-backed reason.")
        trace = node.get("traceability") or {}
        if not trace.get("requirementId") or not trace.get("recommendationId"):
            _finding(findings, "missing_traceability", "Error", node, "Requirement and recommendation traceability are required.")
        proposal_knowledge = set(_strings(proposal.get("knowledgeReferences")))
        node_knowledge = set(_strings(trace.get("knowledgeReferences")))
        if node_knowledge and not node_knowledge.issubset(proposal_knowledge):
            _finding(findings, "knowledge_inconsistency", "Error", node, "Node references knowledge outside the proposal knowledge version.")
    cycles = _dependency_cycles(proposal.get("dependencies") or [], node_ids)
    for node_id in cycles:
        _finding(findings, "circular_dependency", "Error", _node(proposal, node_id), "Circular dependency detected.")
    active_story_ids = {
        node["nodeId"] for node in nodes
        if node.get("type") == "Story" and node.get("status") != "Rejected"
    }
    for criterion in proposal.get("acceptanceCriteria") or []:
        if not active_story_ids.intersection(_strings(criterion.get("mappedNodeIds"))):
            _finding(
                findings, "unmapped_acceptance_criteria", "Error",
                {"nodeId": "", "title": _text(criterion.get("title") or criterion.get("text"))},
                "Acceptance Criterion is not mapped to an active Story.",
            )
    if not _strings(proposal.get("definitionOfDone")):
        _finding(
            findings, "missing_definition_of_done", "Error",
            {"nodeId": "", "title": proposal.get("title")},
            "Planning Proposal requires a Definition of Done.",
        )
    if int((proposal.get("azureDevOpsPreview") or {}).get("writesPerformed") or 0):
        _finding(
            findings, "unsafe_ado_preview", "Error",
            {"nodeId": "", "title": proposal.get("title")},
            "Planning Proposal generation must not perform Azure DevOps writes.",
        )
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
    structural_score = round(coverage * .3 + estimate_score * .2 + repository_score * .2 + trace_score * .3)
    planning_confidence = int(_average([node.get("confidence") for node in nodes]))
    engineering_confidence = int(proposal.get("estimate", {}).get("confidence") or 0)
    quality_penalty = min(
        60,
        sum(12 if item["severity"] == "Error" else 4 for item in findings),
    )
    semantic_quality = max(0, 100 - quality_penalty)
    overall = round(
        structural_score * .45
        + planning_confidence * .30
        + engineering_confidence * .15
        + semantic_quality * .10
    )
    if not mandatory_passed:
        overall = min(overall, 69)
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
        "engineeringConfidence": engineering_confidence,
        "planningConfidence": planning_confidence,
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
        ("Acceptance Traceability", not any(item.get("code") in {"unmapped_acceptance_criteria", "unapproved_acceptance_criteria"} for item in validation.get("findings") or []), True),
        ("Repository Mapping", health.get("repositoryCoverage", 0) > 0, False),
        ("Dependencies", not any(item.get("code") == "circular_dependency" for item in validation.get("findings") or []), True),
        ("Engineering Estimate", health.get("estimateCompleteness", 0) == 100, True),
        ("Story Points", all(node.get("storyPoints") for node in nodes if node.get("type") == "Story"), True),
        (
            "Implementation Order",
            len(proposal.get("implementationOrder") or []) == len([
                node for node in nodes
                if node.get("type") in {"Task", "Sub Task"} and node.get("status") != "Rejected"
            ]),
            True,
        ),
        ("Risk", bool(proposal.get("estimate", {}).get("risk")), True),
        ("Definition of Done", bool(proposal.get("definitionOfDone")), True),
        ("Architecture Review", not any(item.get("code") == "knowledge_inconsistency" for item in validation.get("findings") or []), False),
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
        "unapproved_acceptance_criteria": "Approve, edit, or discard AI-suggested Acceptance Criteria.",
        "unmapped_acceptance_criteria": "Map the Acceptance Criterion to an active Story.",
        "orphan_story": "Generate or add at least one implementation Task for the Story.",
        "missing_estimate": "Regenerate or manually override the engineering estimate.",
        "missing_story_points": "Add Story Points before review.",
        "missing_repository": "Confirm a repository mapping or record that repository context is unavailable.",
        "missing_traceability": "Regenerate the item from its approved requirement boundary.",
        "weak_repository_mapping": "Record why the repository mapping applies.",
        "knowledge_inconsistency": "Refresh the proposal from the approved Knowledge Registry version.",
        "missing_definition_of_done": "Define completion, validation, and testing expectations.",
        "unsafe_ado_preview": "Rebuild the preview without executing Azure DevOps writes.",
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


def _first(values: list[str]) -> str:
    return values[0] if values else ""


def _confidence_value(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("overall") or value.get("score") or value.get("confidence")
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, round(number * 100 if number <= 1 else number)))


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
