"""Mode policies for deterministic prompt prioritization."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SUPPORTED_PROMPT_MODES


@dataclass(frozen=True, slots=True)
class PromptModePolicy:
    mode: str
    objective: str
    instructions: tuple[str, ...]
    section_order: tuple[str, ...]
    appendix_sections: frozenset[str]


_PROTECTED = ("repository_context", "implementation_guidance", "validation")


POLICIES = {
    "implementation": PromptModePolicy(
        "implementation",
        "Implement the approved change with the smallest safe, test-backed edits.",
        ("Follow repository evidence before proposing files or components.", "Satisfy every acceptance criterion and validation expectation."),
        (*_PROTECTED, "instructions", "constraints", "qa", "business_objective"),
        frozenset({"business_objective"}),
    ),
    "bug_fix": PromptModePolicy(
        "bug_fix",
        "Identify the root cause, apply the smallest corrective change, and prevent regression.",
        ("Preserve unrelated behavior.", "Verify the failure path and the corrected path."),
        ("repository_context", "validation", "implementation_guidance", "constraints", "qa", "instructions", "business_objective"),
        frozenset({"business_objective"}),
    ),
    "refactor": PromptModePolicy(
        "refactor",
        "Improve the approved structure while preserving externally observable behavior.",
        ("Do not expand scope or alter behavior without acceptance support.", "Keep compatibility and regression validation explicit."),
        ("repository_context", "validation", "implementation_guidance", "constraints", "qa", "instructions", "business_objective"),
        frozenset({"business_objective"}),
    ),
    "architecture": PromptModePolicy(
        "architecture",
        "Produce a bounded architecture change aligned with repository evidence and approved constraints.",
        ("Explain boundaries, dependencies, and migration impact.", "Do not invent repository components."),
        ("repository_context", "implementation_guidance", "validation", "constraints", "business_objective", "instructions", "qa"),
        frozenset({"qa"}),
    ),
    "review": PromptModePolicy(
        "review",
        "Review the implementation against the approved acceptance, scope, and repository evidence.",
        ("Lead with blocking findings and unsupported changes.", "Do not propose broad unrelated improvements."),
        ("validation", "repository_context", "implementation_guidance", "constraints", "qa", "instructions", "business_objective"),
        frozenset({"business_objective"}),
    ),
    "documentation": PromptModePolicy(
        "documentation",
        "Document the approved engineering behavior accurately from supplied implementation evidence.",
        ("Do not invent behavior, files, APIs, or configuration.", "Keep terminology aligned with the approved artifact."),
        ("implementation_guidance", "repository_context", "validation", "business_objective", "instructions", "constraints", "qa"),
        frozenset({"qa"}),
    ),
    "testing": PromptModePolicy(
        "testing",
        "Create or improve tests that verify every approved acceptance and regression expectation.",
        ("Cover positive, negative, permission, boundary, and regression paths where applicable.", "Use repository evidence to place tests correctly."),
        ("validation", "repository_context", "implementation_guidance", "qa", "constraints", "instructions", "business_objective"),
        frozenset({"business_objective"}),
    ),
    "optimization": PromptModePolicy(
        "optimization",
        "Optimize the approved behavior using measurable evidence without changing its contract.",
        ("Establish a baseline and verify measurable improvement.", "Preserve correctness, permissions, and regression coverage."),
        ("repository_context", "implementation_guidance", "validation", "constraints", "qa", "instructions", "business_objective"),
        frozenset({"business_objective"}),
    ),
}


def resolve_mode(value: str) -> PromptModePolicy:
    normalized = "_".join(str(value or "").strip().casefold().replace("-", " ").split())
    if normalized not in SUPPORTED_PROMPT_MODES:
        supported = ", ".join(mode.replace("_", " ").title() for mode in SUPPORTED_PROMPT_MODES)
        raise ValueError(f"Unsupported prompt mode. Supported modes: {supported}.")
    return POLICIES[normalized]
