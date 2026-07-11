"""Security and planning-boundary filtering for context candidates."""

from __future__ import annotations

from .models import ContextCandidate, ContextRequest, ContextSourceType


class ContextFilter:
    def apply(self, request: ContextRequest, candidates: list[ContextCandidate]) -> tuple[list[ContextCandidate], list[dict]]:
        selected: list[ContextCandidate] = []
        rejected: list[dict] = []
        seen: set[tuple[str, str]] = set()
        minimum = float(request.options.get("minimumConfidence", 0.0) or 0.0)
        blocked_modules = {str(item).casefold() for item in request.options.get("blockedModules", [])}
        blocked_flows = {str(item).casefold() for item in request.options.get("blockedFlows", [])}
        direct_files = any(c.source_type == ContextSourceType.REPOSITORY and c.metadata.get("directEvidence") and c.category in {"File", "Symbol", "API", "Test"} for c in candidates)
        for candidate in candidates:
            reason = ""
            module = str(candidate.metadata.get("module", "")).casefold()
            flow = str(candidate.metadata.get("flow", "")).casefold()
            if candidate.confidence_score < minimum:
                reason = "below_minimum_confidence"
            elif candidate.metadata.get("rejectedPlanning"):
                reason = "rejected_planning_context"
            elif module and module in blocked_modules:
                reason = "blocked_module"
            elif flow and flow in blocked_flows:
                reason = "blocked_flow"
            elif candidate.source_type == ContextSourceType.ENGINEERING_MEMORY and candidate.provenance.get("projectId") not in {None, "", request.project_id} and not request.options.get("allowOrganizationMemoryReuse", False):
                reason = "cross_project_memory_not_permitted"
            elif direct_files and candidate.source_type == ContextSourceType.REPOSITORY and candidate.metadata.get("broadContext"):
                reason = "specific_repository_evidence_preferred"
            key = (candidate.category.casefold(), " ".join(candidate.content.casefold().split()))
            if not reason and key in seen:
                reason = "duplicate_candidate"
            if reason:
                rejected.append({"candidate": candidate, "reason": reason})
            else:
                seen.add(key)
                selected.append(candidate)
        return selected, rejected
