from .base import BaseModelAdapter


class OllamaModelAdapter(BaseModelAdapter):
    model_id = "ollama"
    wording_profile = "compact-local"
    preamble = "Implement only the approved scoped change."
    section_order = ("business_objective", "implementation_guidance", "validation", "repository_context", "constraints", "qa", "instructions")
    title_overrides = {"business_objective": "Objective", "implementation_guidance": "Implementation", "validation": "Validation"}

    def _capability_instructions(self, profile):
        instructions = super()._capability_instructions(profile)
        return instructions[-1:] if instructions else []
