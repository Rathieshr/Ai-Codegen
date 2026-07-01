"""Artifact definitions plug domain intelligence into the generic engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


Strategy = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class ArtifactDefinitionProtocol(Protocol):
    artifact_type: str

    def analyze(self, source: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...

    def generate(self, source: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...

    def validate(self, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...

    def build_dna(self, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...

    def build_prompt(self, artifact: dict[str, Any], context: dict[str, Any]) -> str:
        ...


@dataclass
class ArtifactDefinition:
    artifact_type: str
    analysis_strategy: Strategy | None = None
    generation_strategy: Strategy | None = None
    validation_strategy: Strategy | None = None
    dna_builder: Strategy | None = None
    prompt_builder: Callable[[dict[str, Any], dict[str, Any]], str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def analyze(self, source: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.analysis_strategy(source, context) if self.analysis_strategy else {}

    def generate(self, source: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.generation_strategy(source, context) if self.generation_strategy else {}

    def validate(self, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.validation_strategy(artifact, context) if self.validation_strategy else {}

    def build_dna(self, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.dna_builder(artifact, context) if self.dna_builder else {}

    def build_prompt(self, artifact: dict[str, Any], context: dict[str, Any]) -> str:
        return self.prompt_builder(artifact, context) if self.prompt_builder else ""

