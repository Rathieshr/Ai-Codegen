from .base import BaseModelAdapter


class CodexModelAdapter(BaseModelAdapter):
    model_id = "codex"
    wording_profile = "repository-first"
    preamble = "Implement the approved change in the existing codebase with minimal, test-backed edits."
    section_order = ("instructions", "implementation_guidance", "repository_context", "validation", "qa", "constraints", "business_objective")
    title_overrides = {"repository_context": "Repository Evidence", "validation": "Acceptance Contract", "instructions": "Working Rules"}
