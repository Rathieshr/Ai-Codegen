"""Versioned, reusable templates for engineering reasoning workflows."""

from __future__ import annotations

from dataclasses import dataclass


PROMPT_VERSION = "hei-reasoning-v1"


@dataclass(frozen=True)
class PromptTemplate:
    workflow: str
    role: str
    objective: str
    instructions: tuple[str, ...]


_COMMON = (
    "Use only the supplied Engineering Context.",
    "Do not invent repository files, modules, APIs, dependencies, memory, or Azure DevOps work items.",
    "Reference evidence by referenceId.",
    "Explain why, alternatives considered, risks, trade-offs, and impact.",
    "Return only one JSON object matching the output schema.",
)


TEMPLATES: dict[str, PromptTemplate] = {
    "requirement_intent_analysis": PromptTemplate(
        "Requirement Intent Analysis", "Senior Product and Business Analyst",
        "Interpret the supplied requirement into bounded search intent for Engineering Intelligence.",
        (
            "Treat every output as an interpretation or search hint, never as repository fact.",
            "Do not invent files, modules, APIs, work items, dependencies, or implementation details.",
            "Use only the requirement and bounded project metadata supplied in this prompt.",
            "Separate the business outcome from functional intent.",
            "Return only one JSON object matching the output schema.",
        ),
    ),
    "requirement_evidence_synthesis": PromptTemplate(
        "Requirement Evidence Synthesis", "Senior Engineering Business Analyst",
        "Synthesize a final requirement analysis from the original requirement and discovered engineering evidence.",
        _COMMON + (
            "Use Requirement Intent only as interpretation; Engineering Context is authoritative for engineering facts.",
            "State missing information only after checking repository, Markdown, Azure DevOps, knowledge, and memory evidence.",
            "Keep source-derived, AI-inferred, and evidence-backed findings distinguishable.",
        ),
    ),
    "requirement_analysis": PromptTemplate(
        "Requirement Analysis", "Senior Business Analyst",
        "Assess requirement quality and recommend evidence-backed improvements.",
        _COMMON + ("Distinguish source facts, missing information, and recommendations.",),
    ),
    "acceptance_criteria_generation": PromptTemplate(
        "Acceptance Criteria Generation", "Senior Business Analyst and QA Lead",
        "Generate measurable, implementation-independent Acceptance Criteria from approved requirement facts.",
        _COMMON + (
            "Generate criteria only for supplied functional requirements, business rules, and measurable constraints.",
            "Use Given, When, Then wording and map every criterion to a supplied functional requirement.",
            "Do not turn missing information or assumptions into official requirements.",
        ),
    ),
    "planning_recommendation": PromptTemplate(
        "Planning Recommendation", "Product Manager and Solution Architect",
        "Recommend how approved requirements should fit the existing engineering landscape.",
        _COMMON + ("Prefer reuse or extension when evidence supports it.",),
    ),
    "planning_proposal": PromptTemplate(
        "Planning Proposal", "Engineering Planning Lead",
        "Propose a scoped, non-duplicative engineering hierarchy.",
        _COMMON + ("Keep every proposal traceable to the requirement and selected evidence.",),
    ),
    "execution_package": PromptTemplate(
        "Execution Package", "Principal Engineer",
        "Improve implementation guidance within the approved implementation boundary.",
        _COMMON + ("Do not expand scope or invent repository paths.",),
    ),
    "validation": PromptTemplate(
        "Validation", "Engineering Validation Lead",
        "Assess alignment with approved scope, acceptance criteria, and engineering evidence.",
        _COMMON + ("Clearly distinguish verified, partially verified, and unverifiable findings.",),
    ),
    "risk_analysis": PromptTemplate(
        "Risk Analysis", "Engineering Risk Lead",
        "Identify evidence-backed implementation, integration, security, and regression risks.",
        _COMMON + ("Do not infer a risk from absent evidence without marking it as uncertainty.",),
    ),
    "architecture_review": PromptTemplate(
        "Architecture Review", "Enterprise Architect",
        "Review architecture alignment and trade-offs against known architecture evidence.",
        _COMMON + ("Treat repository architecture facts as authoritative.",),
    ),
    "code_review": PromptTemplate(
        "Code Review", "Senior Engineering Reviewer",
        "Review structured implementation evidence against approved engineering context.",
        _COMMON + ("Do not claim code behavior that is not present in supplied evidence.",),
    ),
}


def resolve_template(workflow_type: str) -> PromptTemplate:
    key = _key(workflow_type)
    return TEMPLATES.get(key) or PromptTemplate(
        workflow_type or "Engineering Reasoning",
        "Senior Engineering Advisor",
        "Produce an evidence-backed engineering recommendation.",
        _COMMON,
    )


def _key(value: str) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", " ").split())
