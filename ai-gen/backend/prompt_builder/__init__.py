"""Prompt builder package for ai-gen pipeline.

SDLC order enforced:
  1. BA approved  → build_ui_prompt()    (designer / PO reviews UI spec)
  2. UI approved  → build_dev_prompt()   (developer / Copilot implements)

Provides two public functions:
    build_ui_prompt(ba_output, ui_output, work_item) -> str
    build_dev_prompt(ba_output, ui_output, dev_output, repo_context, work_item) -> str

Both return structured prompt strings optimised for GitHub Copilot Chat,
Cursor, or any LLM-based code assistant.
"""

from .dev_prompt import build_dev_prompt
from .ui_prompt import build_ui_prompt

__all__ = ["build_dev_prompt", "build_ui_prompt"]
