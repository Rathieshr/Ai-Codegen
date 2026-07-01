"""State machine used by all HEI planning artifact types."""

from __future__ import annotations

from .artifact_lifecycle import ArtifactStatus, LIFECYCLE_ORDER, LifecycleResult, TERMINAL_STATUSES


class ArtifactStateMachine:
    """Small deterministic lifecycle machine shared by every artifact."""

    _event_targets = {
        "analyze": ArtifactStatus.ANALYSIS,
        "review": ArtifactStatus.REVIEW,
        "approve": ArtifactStatus.APPROVED,
        "reject": ArtifactStatus.REJECTED,
        "generate": ArtifactStatus.GENERATION,
        "validate": ArtifactStatus.VALIDATION,
        "build_dna": ArtifactStatus.DNA,
        "version": ArtifactStatus.VERSIONED,
        "publish": ArtifactStatus.PUBLISHED,
    }

    def can_transition(self, current_status: str, event: str) -> tuple[bool, str]:
        target = self._event_targets.get(event)
        if not target:
            return False, f"Unknown artifact lifecycle event: {event}."
        if current_status in TERMINAL_STATUSES:
            return False, f"Artifact is {current_status} and cannot transition via {event}."
        if event == "reject":
            return True, ""
        if event == "approve":
            return current_status in {ArtifactStatus.REVIEW, ArtifactStatus.VALIDATION, ArtifactStatus.DNA, ArtifactStatus.VERSIONED}, (
                "Artifact must be in Review, Validation, DNA, or Versioned before approval."
            )
        if event == "publish":
            return current_status in {ArtifactStatus.APPROVED, ArtifactStatus.VERSIONED}, "Artifact must be approved or versioned before publishing."
        if event == "generate":
            return current_status in {ArtifactStatus.APPROVED, ArtifactStatus.REVIEW, ArtifactStatus.ANALYSIS}, (
                "Artifact must be analyzed, reviewed, or approved before generation."
            )
        if event in {"validate", "build_dna", "version"}:
            return current_status in {ArtifactStatus.GENERATION, ArtifactStatus.VALIDATION, ArtifactStatus.DNA, ArtifactStatus.APPROVED}, (
                "Artifact must be generated before validation, DNA, or versioning."
            )
        if current_status == ArtifactStatus.DRAFT:
            return event == "analyze", "Draft artifacts must be analyzed first."
        if current_status in LIFECYCLE_ORDER:
            current_index = LIFECYCLE_ORDER.index(current_status)
            target_index = LIFECYCLE_ORDER.index(target) if target in LIFECYCLE_ORDER else current_index
            return target_index >= current_index, "Lifecycle cannot move backwards without regeneration."
        return True, ""

    def transition(self, artifact_id: str, current_status: str, event: str) -> LifecycleResult:
        allowed, reason = self.can_transition(current_status, event)
        target = self._event_targets.get(event, current_status)
        return LifecycleResult(
            artifact_id=artifact_id,
            previous_status=current_status,
            status=target if allowed else current_status,
            event=event,
            allowed=allowed,
            reason="" if allowed else reason,
        )

