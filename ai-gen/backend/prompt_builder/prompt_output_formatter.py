"""Readable output formatting for Developer Prompt V2."""

from __future__ import annotations

from typing import Any

from backend.prompt_budget import PromptSection, estimateTokens

from .developer_prompt_model import clean


def format_developer_prompt(sections: list[PromptSection]) -> str:
    section_map = {section.id: section for section in sections}
    ordered_ids = [
        "role",
        "objective",
        "current_work_item",
        "current_intent",
        "dna",
        "validation",
        "planning_boundary",
        "repository_evidence",
        "knowledge_summary",
        "risks",
        "required_tests",
        "instructions",
        "output_schema",
    ]
    parts: list[str] = ["# Developer Prompt V2", ""]
    for section_id in ordered_ids:
        section = section_map.get(section_id)
        if not section:
            continue
        content = _format_content(section.id, section.content)
        if not clean(content):
            continue
        parts.append(f"## {section.name}")
        parts.append(content)
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def prompt_tokens(prompt: str) -> int:
    return estimateTokens(prompt)


def _format_content(section_id: str, content: Any) -> str:
    if section_id == "current_work_item":
        return _task_context(content)
    if section_id == "current_intent":
        return _story_context(content)
    if section_id == "dna":
        return _engineering_dna(content)
    if section_id == "validation":
        return _acceptance_mapping(content)
    if section_id == "planning_boundary":
        return _boundary(content)
    if section_id == "repository_evidence":
        return _repository(content)
    if section_id == "knowledge_summary":
        return _bullet_list(content, empty="Follow existing codebase standards.")
    if section_id == "risks":
        return _bullet_list(content, empty="No implementation risks identified.")
    if section_id == "required_tests":
        return _tests(content)
    if section_id in {"instructions", "output_schema"}:
        return _bullet_list(content)
    if isinstance(content, str):
        return content
    return _bullet_list(content)


def _task_context(content: Any) -> str:
    data = content if isinstance(content, dict) else {}
    lines = [
        f"- Task: {clean(data.get('taskTitle')) or clean(data.get('taskObjective')) or 'Selected task'}",
        f"- Objective: {clean(data.get('taskObjective')) or 'Implement the selected task.'}",
        f"- DNA Version: {data.get('taskDNAVersion') or 'unknown'}",
        f"- Package: {data.get('packageId') or 'unknown'}",
    ]
    scope = data.get("taskScope") if isinstance(data.get("taskScope"), list) else []
    if scope:
        lines.append("- Task Scope:")
        lines.extend(f"  - {clean(item)}" for item in scope if clean(item))
    return "\n".join(lines)


def _story_context(content: Any) -> str:
    data = content if isinstance(content, dict) else {}
    lines = [
        f"- Story: {clean(data.get('storyTitle')) or data.get('storyId') or 'unknown'}",
        f"- Story ID: {data.get('storyId') or 'unknown'}",
        f"- User Goal: {clean(data.get('storyUserGoal')) or 'Use the parent story goal from the execution package.'}",
    ]
    criteria = data.get("relevantAcceptanceCriteria") if isinstance(data.get("relevantAcceptanceCriteria"), list) else []
    if criteria:
        lines.append("- Relevant Acceptance Criteria:")
        for item in criteria:
            if isinstance(item, dict):
                lines.append(f"  - {clean(item.get('id'))}: {clean(item.get('text'))}")
    return "\n".join(lines)


def _acceptance_mapping(content: Any) -> str:
    items = content if isinstance(content, list) else []
    if not items:
        return "No acceptance criteria mapping available. Stop and ask for clarification before coding."
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(f"- {clean(item.get('id')) or 'AC'}: {clean(item.get('text'))}")
        lines.append(f"  - Implementation: {clean(item.get('implementation')) or 'Map this AC to the selected task.'}")
        lines.append(f"  - Validation: {clean(item.get('validation')) or 'Add tests for this AC.'}")
    return "\n".join(lines)


def _engineering_dna(content: Any) -> str:
    data = content if isinstance(content, dict) else {}
    evidence = data.get("repositoryEvidence") if isinstance(data.get("repositoryEvidence"), dict) else {}
    lines = [
        f"- Capability: {clean(data.get('capability')) or 'Not captured'}",
    ]
    responsibilities = data.get("responsibilities") if isinstance(data.get("responsibilities"), list) else []
    if responsibilities:
        lines.append(f"- Responsibilities: {', '.join(clean(item) for item in responsibilities if clean(item))}")
    modules = evidence.get("modules") if isinstance(evidence.get("modules"), list) else []
    flows = evidence.get("flows") if isinstance(evidence.get("flows"), list) else []
    if modules:
        lines.append(f"- Repository Modules: {', '.join(clean(item) for item in modules if clean(item))}")
    if flows:
        lines.append(f"- Repository Flows: {', '.join(clean(item) for item in flows if clean(item))}")
    return "\n".join(lines)


def _boundary(content: Any) -> str:
    data = content if isinstance(content, dict) else {}
    labels = [
        ("In scope", "inScope"),
        ("Out of scope", "outOfScope"),
        ("Allowed modules", "allowedModules"),
        ("Blocked modules", "blockedModules"),
        ("Allowed flows", "allowedFlows"),
        ("Blocked flows", "blockedFlows"),
        ("Assumptions", "assumptions"),
        ("Constraints", "constraints"),
    ]
    lines: list[str] = []
    for label, key in labels:
        values = data.get(key) if isinstance(data.get(key), list) else []
        if values:
            lines.append(f"- {label}:")
            lines.extend(f"  - {clean(item)}" for item in values if clean(item))
    return "\n".join(lines) or "- Use the approved execution package boundary only."


def _repository(content: Any) -> str:
    data = content if isinstance(content, dict) else {}
    files = data.get("files") if isinstance(data.get("files"), list) else []
    status = clean(data.get("fileRankingStatus"))
    lines: list[str] = []
    if files:
        lines.append("- Repository-ranked items:")
        for item in files:
            if isinstance(item, dict):
                confidence = item.get("confidence")
                confidence_text = f" confidence={confidence}" if confidence not in ("", None) else ""
                lines.append(f"  - {clean(item.get('name'))} ({clean(item.get('type')) or 'file'}{confidence_text}): {clean(item.get('reason'))}")
    else:
        lines.append("- Repository file ranking not available. Do not invent file paths. Locate the closest existing implementation before editing.")
    for key, label in [("services", "Services"), ("apis", "APIs"), ("modules", "Modules"), ("flows", "Flows")]:
        values = data.get(key) if isinstance(data.get(key), list) else []
        if values:
            lines.append(f"- {label}:")
            for item in values[:6]:
                if isinstance(item, dict):
                    lines.append(f"  - {clean(item.get('name'))}: {clean(item.get('reason'))}")
    if status and status != "Repository file ranking not available":
        lines.append(f"- File ranking: {status}")
    return "\n".join(lines)


def _tests(content: Any) -> str:
    items = content if isinstance(content, list) else []
    if not items:
        return "- Add unit, integration, negative, permission, and regression tests for the mapped acceptance criteria."
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        coverage = item.get("coverage") if isinstance(item.get("coverage"), list) else []
        suffix = f" Covers: {', '.join(str(value) for value in coverage)}." if coverage else ""
        lines.append(f"- {clean(item.get('type')).title() or 'Test'}: {clean(item.get('title'))}.{suffix}")
    return "\n".join(lines)


def _bullet_list(content: Any, *, empty: str = "") -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        values = [clean(item) if not isinstance(item, dict) else clean(item.get("rule") or item.get("risk") or item.get("title") or item.get("name")) for item in content]
        values = [value for value in values if value]
        return "\n".join(f"- {value}" for value in values) if values else empty
    if isinstance(content, dict):
        return "\n".join(f"- {key}: {value}" for key, value in content.items() if value)
    return clean(content) or empty
