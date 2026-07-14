from .base import BaseModelAdapter


class GeminiModelAdapter(BaseModelAdapter):
    model_id = "gemini"
    wording_profile = "context-synthesis"
    preamble = "Integrate the supplied repository evidence and engineering guidance into one bounded implementation."
    section_order = ("business_objective", "repository_context", "implementation_guidance", "constraints", "validation", "qa", "instructions")
    title_overrides = {"repository_context": "Grounded Repository Context", "qa": "Verification Coverage"}
