from .base import BaseModelAdapter


class GPTModelAdapter(BaseModelAdapter):
    model_id = "gpt"
    wording_profile = "balanced-reasoning"
    preamble = "Produce a scoped implementation that satisfies the approved acceptance and validation contract."
    section_order = ("business_objective", "implementation_guidance", "repository_context", "validation", "constraints", "qa", "instructions")
    title_overrides = {"validation": "Acceptance & Validation", "qa": "Required QA"}
