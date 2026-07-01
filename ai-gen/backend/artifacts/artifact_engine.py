"""Generic Artifact Engine for HEI planning and execution assets."""

from __future__ import annotations

from typing import Any

from .artifact_factory import ArtifactFactory
from .artifact_lifecycle import ArtifactStatus
from .artifact_repository import ArtifactRepository
from .artifact_state_machine import ArtifactStateMachine
from .artifact_validator import ArtifactValidator
from .artifact_version_manager import ArtifactVersionManager


class ArtifactEngine:
    """Shared orchestration engine for Epic, Feature, Story, Task, and future artifacts."""

    def __init__(
        self,
        factory: ArtifactFactory | None = None,
        repository: ArtifactRepository | None = None,
        state_machine: ArtifactStateMachine | None = None,
        validator: ArtifactValidator | None = None,
        version_manager: ArtifactVersionManager | None = None,
    ) -> None:
        self.factory = factory or ArtifactFactory()
        self.repository = repository or ArtifactRepository()
        self.state_machine = state_machine or ArtifactStateMachine()
        self.validator = validator or ArtifactValidator()
        self.version_manager = version_manager or ArtifactVersionManager()

    def create(self, artifact_type: str, source: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        artifact = self.factory.create(artifact_type, source, context)
        return self.repository.save(artifact)

    def analyze(self, artifact: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._run_stage(artifact, context, "analyze", lambda definition, item, ctx: definition.analyze(item, ctx))

    def generate(self, artifact: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._run_stage(artifact, context, "generate", lambda definition, item, ctx: definition.generate(item, ctx))

    def validate(self, artifact: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        definition = self.factory.definition_for(str(artifact.get("type") or "Artifact"))
        report = self.validator.validate_with_definition(artifact, definition.validate(artifact, context))
        updated = {**artifact, "validation": report}
        transitioned = self._transition(updated, "validate")
        return self.repository.save(transitioned)

    def approve(self, artifact: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        updated = self._transition(artifact, "approve")
        updated["approved"] = updated["status"] == ArtifactStatus.APPROVED
        return self.repository.save(updated)

    def reject(self, artifact: dict[str, Any], reason: str = "") -> dict[str, Any]:
        updated = self._transition(artifact, "reject")
        updated["rejectionReason"] = reason
        return self.repository.save(updated)

    def build_dna(self, artifact: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._run_stage(artifact, context, "build_dna", lambda definition, item, ctx: {"dna": definition.build_dna(item, ctx)})

    def version(self, artifact: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
        versioned = self.version_manager.next_version(artifact, previous)
        versioned = self._transition(versioned, "version")
        return self.repository.save(versioned)

    def publish(self, artifact: dict[str, Any]) -> dict[str, Any]:
        return self.repository.save(self._transition(artifact, "publish"))

    def _run_stage(self, artifact: dict[str, Any], context: dict[str, Any] | None, event: str, runner: Any) -> dict[str, Any]:
        context = context or {}
        definition = self.factory.definition_for(str(artifact.get("type") or "Artifact"))
        stage_payload = runner(definition, artifact, context)
        updated = {**artifact, **(stage_payload or {})}
        updated = self._transition(updated, event)
        return self.repository.save(updated)

    def _transition(self, artifact: dict[str, Any], event: str) -> dict[str, Any]:
        result = self.state_machine.transition(str(artifact.get("id") or ""), str(artifact.get("status") or ArtifactStatus.DRAFT), event)
        history = list(artifact.get("lifecycleHistory") or [])
        history.append(
            {
                "event": event,
                "from": result.previous_status,
                "to": result.status,
                "allowed": result.allowed,
                "reason": result.reason,
            }
        )
        return {**artifact, "status": result.status, "lifecycleHistory": history}

