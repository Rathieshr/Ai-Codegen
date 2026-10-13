from __future__ import annotations

from typing import Any, Protocol

from .artifact_generator import ArtifactGenerator
from .prompt_builder import PROMPT_SECTIONS, PromptBuilder
from .reasoning_diagnostics import reasoning_diagnostics


class PlanningLLMProvider(Protocol):
    def generate_json(self, prompt: str, output_type: str) -> dict[str, Any]:
        ...


class PlanningReasoner:
    def __init__(self, provider: PlanningLLMProvider | None = None) -> None:
        self.provider = provider
        self.prompt_builder = PromptBuilder()
        self.artifacts = ArtifactGenerator()

    def generate_planning_artifact(
        self,
        planning_context: dict[str, Any],
        output_type: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        _validate_planning_context(planning_context)
        prompt = self.prompt_builder.build(planning_context, output_type)
        provider = options.get("llm_provider") or options.get("provider") or self.provider
        provider_payload: dict[str, Any] | None = None
        provider_used = "deterministic_fallback"
        if provider and not options.get("deterministic_only"):
            provider_used = "llm"
            provider_payload = provider.generate_json(prompt, output_type)
        artifacts, warnings = self.artifacts.generate(planning_context, output_type, provider_payload)
        return {
            "outputType": output_type,
            "artifacts": artifacts,
            "prompt": prompt,
            "diagnostics": reasoning_diagnostics(
                output_type=output_type,
                prompt=prompt,
                provider_used=provider_used,
                prompt_sections=PROMPT_SECTIONS,
                duplicate_count=sum(1 for item in artifacts if item.get("duplicateCandidate")),
                validation_warnings=warnings,
            ),
        }


def generate_planning_artifact(planning_context: dict[str, Any], output_type: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    provider = (options or {}).get("llm_provider") or (options or {}).get("provider")
    return PlanningReasoner(provider=provider).generate_planning_artifact(planning_context, output_type, options)


def generatePlanningArtifact(planningContext: dict[str, Any], outputType: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate_planning_artifact(planningContext, outputType, options)


def _validate_planning_context(planning_context: dict[str, Any]) -> None:
    if not isinstance(planning_context, dict):
        raise ValueError("PlanningContext must be a dictionary.")
    forbidden = ["knowledge_registry", "knowledgeRegistry", "projectProfile", "project_profile", "repositorySnapshot", "repository_snapshot"]
    present = [key for key in forbidden if key in planning_context]
    if present:
        raise ValueError(f"PlanningReasoner accepts PlanningContext only; remove broad context keys: {', '.join(present)}")
    required = ["businessGoal", "userProblem", "expectedOutcome", "selectedCapabilities"]
    missing = [key for key in required if key not in planning_context]
    if missing:
        raise ValueError(f"PlanningContext missing required field(s): {', '.join(missing)}")

