from .base import BaseModelAdapter


class GLMModelAdapter(BaseModelAdapter):
    model_id = "glm"
    wording_profile = "structured-concise"
    preamble = "Implement the approved objective within the supplied scope, repository evidence, and validation rules."
    section_order = ("instructions", "business_objective", "implementation_guidance", "validation", "repository_context", "constraints", "qa")
    title_overrides = {"implementation_guidance": "Implementation Steps", "validation": "Required Validation"}
