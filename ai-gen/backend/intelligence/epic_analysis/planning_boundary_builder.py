from __future__ import annotations

from .epic_analysis import CapabilityCandidate, PlanningBoundary


def build_planning_boundary(required: list[CapabilityCandidate], excluded: list[CapabilityCandidate]) -> PlanningBoundary:
    in_scope = [item.name for item in required]
    out_of_scope = [item.name for item in excluded]
    return PlanningBoundary(in_scope=_unique(in_scope), out_of_scope=_unique(out_of_scope))


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
