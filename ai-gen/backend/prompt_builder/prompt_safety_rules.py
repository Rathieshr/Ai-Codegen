"""Safety rules for Developer Prompt V2."""

from __future__ import annotations


DEFAULT_DO_NOT_TOUCH = [
    "Do not modify unrelated modules.",
    "Do not create fake services, APIs, repositories, view models, screens, or file paths.",
    "Do not invent file paths. If repository ranking is unavailable, inspect the codebase first.",
    "Do not change authentication or authorization flow unless it is explicitly in scope.",
    "Do not change firmware, rollout, rollback, or device update behavior unless explicitly required.",
    "Do not introduce broad refactors.",
    "Do not regenerate planning content or reinterpret the epic, feature, story, or task.",
]


OUTPUT_REQUIREMENTS = [
    "Summarize the planned changes first.",
    "List files to inspect or change before editing.",
    "Implement minimal safe changes only.",
    "Include or update tests for the mapped acceptance criteria.",
    "Do not change unrelated behavior.",
    "Explain assumptions and any missing repository evidence.",
]
