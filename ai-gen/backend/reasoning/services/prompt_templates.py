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
    "requirement_refinement": PromptTemplate(
        "Requirement Refinement", "Experienced Product Owner and Business Analyst",
        "Transform the source into a clearer engineering requirement while preserving its business intent.",
        (
            "Use only the raw requirement and bounded product/project terminology supplied in this prompt.",
            "Rewrite noticeably when clarity, structure, actor, action, outcome, or terminology can be improved.",
            "Preserve the original meaning and explicitly stated scope; refinement is not feature discovery.",
            "Separate the executive summary, business goal, user intent, expected outcome, capabilities, entities, and concepts.",
            "The business goal must describe the outcome or value and must not repeat the functional user intent.",
            "Extract meaningful repository, Markdown, Azure DevOps, module, and feature search hints from source terminology.",
            "Search hints are candidates for later discovery, not claims that engineering artifacts exist.",
            "Do not invent functionality, business rules, architecture, APIs, acceptance criteria, constraints, or dependencies.",
            "Do not add authentication, authorization, CRUD, validation, audit, notifications, caching, retry, or role management unless explicitly stated.",
            "Identify ambiguity; do not silently resolve it. Return clarification candidates instead.",
            "Explain each material wording change and the reasoning behind the refinement.",
            "Treat repository, Markdown, and Azure DevOps terms as search hints only, never as facts.",
            "Return only one JSON object matching the output schema.",
        ),
    ),
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
        "Write a complete, planning-ready engineering requirement from the refined requirement and discovered engineering evidence.",
        _COMMON + (
            "Use Requirement Intent only as interpretation; Engineering Context is authoritative for engineering facts.",
            "Write the Executive Summary, Problem Statement, Business Goal, Business Value, actors, capabilities, and Functional Requirements as distinct concepts.",
            "The Business Goal must explain why the outcome matters; Functional Requirements must state what behavior is required.",
            "Business Rules, constraints, dependencies, and repository impact require valid evidence references.",
            "Candidate Non-Functional Requirements and assumptions are proposals and must be labelled as such.",
            "Risks may be inferred, but explain the evidence or uncertainty behind each risk.",
            "State missing information only after checking repository, Markdown, Azure DevOps, knowledge, and memory evidence.",
            "Ask an Open Question only when the supplied evidence cannot answer it.",
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
