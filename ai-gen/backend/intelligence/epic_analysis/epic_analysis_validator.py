from __future__ import annotations

from typing import Any

from .epic_analysis import CapabilityCandidate, CapabilityRelationship, PlanningBoundary


def validate_epic_analysis(
    required: list[CapabilityCandidate],
    excluded: list[CapabilityCandidate],
    relationships: list[CapabilityRelationship],
    boundary: PlanningBoundary,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    required_names = [item.name for item in required]
    duplicates = sorted({name for name in required_names if required_names.count(name) > 1})
    if duplicates:
        issues.append({"severity": "Error", "category": "Duplicate Capabilities", "message": f"Duplicate capabilities removed: {', '.join(duplicates)}."})
    excluded_overlap = sorted(set(required_names) & {item.name for item in excluded})
    if excluded_overlap:
        issues.append({"severity": "Error", "category": "Planning Boundary", "message": f"Capabilities cannot be both in and out of scope: {', '.join(excluded_overlap)}."})
    unsupported = [item.name for item in required if item.confidence < 0.5]
    if unsupported:
        issues.append({"severity": "Warning", "category": "Repository Support", "message": f"Low support capabilities require review: {', '.join(unsupported)}."})
    if required and not relationships:
        issues.append({"severity": "Warning", "category": "Graph Connectivity", "message": "No capability relationships were identified."})
    status = "Approved" if not any(issue["severity"] == "Error" for issue in issues) else "Rejected"
    return {
        "status": status,
        "issues": issues,
        "capability_count": len(required),
        "excluded_capability_count": len(excluded),
        "relationship_count": len(relationships),
        "in_scope_count": len(boundary.in_scope),
        "out_of_scope_count": len(boundary.out_of_scope),
    }
