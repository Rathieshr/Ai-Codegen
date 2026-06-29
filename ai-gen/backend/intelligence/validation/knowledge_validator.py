from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import artifact_text, names


def validate_knowledge_alignment(planning_context: dict[str, Any], artifact: dict[str, Any], options: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    standards = names(planning_context.get("selectedStandards"))
    text = artifact_text(artifact)
    issues: list[ValidationIssue] = []
    score = 76
    if standards:
        matched = [standard for standard in standards if standard.lower() in text.lower()]
        score += min(len(matched), 3) * 6
        if not matched:
            issues.append(
                ValidationIssue(
                    "Warning",
                    "Knowledge Alignment",
                    "Artifact does not reference selected standards.",
                    "Add validation, architecture, security, or traceability expectations from selected standards.",
                )
            )
    knowledge = options.get("knowledge_registry") or options.get("knowledgeRegistry") or {}
    terminology = [str(item) for item in knowledge.get("terminology", [])] if isinstance(knowledge, dict) else []
    if terminology and not any(term.lower() in text.lower() for term in terminology):
        issues.append(ValidationIssue("Info", "Knowledge Alignment", "Artifact does not use known project terminology.", "Consider using approved project terminology where relevant."))
    return min(score, 100), issues

