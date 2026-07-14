from .base import BaseModelAdapter


class QwenModelAdapter(BaseModelAdapter):
    model_id = "qwen"
    wording_profile = "implementation-first"
    preamble = "Plan the smallest safe code change, implement it, and verify every acceptance criterion."
    section_order = ("implementation_guidance", "repository_context", "business_objective", "validation", "qa", "constraints", "instructions")
    title_overrides = {"implementation_guidance": "Implementation Plan", "validation": "Acceptance Checks"}
