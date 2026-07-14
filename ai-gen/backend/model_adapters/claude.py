from .base import BaseModelAdapter


class ClaudeModelAdapter(BaseModelAdapter):
    model_id = "claude"
    wording_profile = "constraint-first"
    preamble = "Analyze the approved boundaries and evidence, then implement only the supported engineering change."
    section_order = ("business_objective", "constraints", "repository_context", "implementation_guidance", "validation", "qa", "instructions")
    title_overrides = {"constraints": "Boundaries & Risks", "validation": "Acceptance & Verification"}
