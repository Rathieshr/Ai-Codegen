"""Parse and filter ai-gen Azure DevOps comments."""

from __future__ import annotations

from typing import Any


HEADER_PREFIXES = {
    "[ai-gen clarification]": "clarification",
    "[ai-gen approval]": "approval",
    "[ai-gen handoff]": "handoff",
    "[ai-gen revision]": "revision",
}

STAGE_ALIASES = {
    "ba": "ba",
    "business analyst": "ba",
    "ui": "ui",
    "ui optional": "ui_optional",
    "ui plan": "ui_plan",
    "ui handoff": "ui_handoff",
    "dev": "dev",
    "dev packet": "dev_packet",
    "fix packet": "fix_packet",
    "task analysis": "task_analysis",
    "task planning": "task_planning",
    "test": "test",
    "test planning": "test_planning",
    "test design": "test_design",
    "test checklist": "test_checklist",
    "regression tests": "regression_tests",
    "critic": "critic",
    "epic analysis": "epic_analysis",
    "feature analysis": "feature_analysis",
    "feature generation": "feature_generation",
    "story generation": "story_generation",
    "review": "review",
    "bug analysis": "bug_analysis",
    "impact analysis": "impact_analysis",
    "research plan": "research_plan",
    "findings": "findings",
    "recommendation": "recommendation",
    "automation draft optional": "automation_draft_optional",
}


def parse_ai_gen_comment(comment_text: str) -> dict[str, Any] | None:
    """Parse a single ai-gen comment block into structured metadata."""

    raw = str(comment_text or "").strip()
    if not raw:
        return None
    lines = [line.rstrip() for line in raw.splitlines()]
    header = lines[0].strip().lower()
    comment_type = HEADER_PREFIXES.get(header)
    if not comment_type:
        return None

    metadata: dict[str, Any] = {
        "type": comment_type,
        "stage": "unknown",
        "pipeline_id": None,
        "work_item_id": None,
        "handoff_id": None,
        "author": None,
        "body": "",
        "raw": raw,
    }
    body_lines: list[str] = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("stage:"):
            metadata["stage"] = _normalize_stage(stripped.split(":", 1)[1].strip())
            continue
        if lowered.startswith("pipeline:") or lowered.startswith("pipeline id:"):
            metadata["pipeline_id"] = stripped.split(":", 1)[1].strip() or None
            continue
        if lowered.startswith("work item:") or lowered.startswith("work item id:"):
            metadata["work_item_id"] = stripped.split(":", 1)[1].strip() or None
            continue
        if lowered.startswith("handoff:") or lowered.startswith("handoff id:"):
            metadata["handoff_id"] = stripped.split(":", 1)[1].strip() or None
            continue
        if lowered.startswith("author:"):
            metadata["author"] = stripped.split(":", 1)[1].strip() or None
            continue
        body_lines.append(stripped)
    metadata["body"] = "\n".join(body_lines).strip()
    return metadata


def filter_ai_gen_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter flexible Azure DevOps comments down to parsed ai-gen comments."""

    output: list[dict[str, Any]] = []
    for comment in comments or []:
        if not isinstance(comment, dict):
            continue
        text = _extract_text(comment)
        parsed = parse_ai_gen_comment(text)
        if not parsed:
            continue
        if comment.get("id") is not None:
            parsed["id"] = comment.get("id")
        parsed["created_by"] = _extract_actor(comment.get("created_by") or comment.get("createdBy"))
        parsed["created_at"] = str(comment.get("created_at") or comment.get("createdDate") or comment.get("publishedDate") or "").strip() or None
        output.append(parsed)
    return output


def _extract_text(comment: dict[str, Any]) -> str:
    for key in ("text", "comment", "body"):
        value = comment.get(key)
        if isinstance(value, str) and value.strip():
            return value
    rendered = comment.get("renderedText") or comment.get("html")
    return str(rendered or "").strip()


def _extract_actor(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("displayName", "name", "uniqueName"):
            text = str(value.get(key, "")).strip()
            if text:
                return text
        return None
    text = str(value or "").strip()
    return text or None


def _normalize_stage(value: str) -> str:
    normalized = " ".join(str(value or "").strip().lower().replace("_", " ").split())
    if not normalized:
        return "unknown"
    return STAGE_ALIASES.get(normalized, normalized.replace(" ", "_"))
