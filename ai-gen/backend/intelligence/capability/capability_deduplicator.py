from __future__ import annotations

from .capability_context import CapabilityMatch, RejectedCapability
from .capability_diagnostics import CapabilityDiagnostics
from .capability_rules import CAPABILITY_PURPOSE_GROUPS


def dedupe_capabilities(
    matches: list[CapabilityMatch],
    diagnostics: CapabilityDiagnostics,
) -> tuple[list[CapabilityMatch], list[RejectedCapability]]:
    accepted: list[CapabilityMatch] = []
    rejected: list[RejectedCapability] = []
    seen_names: set[str] = set()
    seen_purposes: dict[str, CapabilityMatch] = {}
    for match in sorted(matches, key=lambda item: item.confidence, reverse=True):
        if match.name in seen_names:
            rejected.append(RejectedCapability(match.name, "Duplicate capability name already selected.", 0.86))
            continue
        purpose = CAPABILITY_PURPOSE_GROUPS.get(match.name, match.name)
        existing = seen_purposes.get(purpose)
        if existing and _can_merge_purpose(existing.name, match.name):
            rejected.append(
                RejectedCapability(
                    match.name,
                    f"Capability overlaps with {existing.name}; each selected capability must answer a distinct user problem.",
                    0.78,
                )
            )
            diagnostics.add(f"Deduplicated {match.name} because it overlaps with {existing.name}.")
            continue
        accepted.append(match)
        seen_names.add(match.name)
        seen_purposes[purpose] = match
    return accepted, rejected


def _can_merge_purpose(existing: str, candidate: str) -> bool:
    if {existing, candidate} == {"Authentication", "Authorization"}:
        return False
    if {existing, candidate} == {"Alert Management", "Notification"}:
        return False
    if {existing, candidate} == {"Reporting", "Export and Reporting"}:
        return False
    return True

