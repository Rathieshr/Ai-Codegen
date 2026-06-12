"""Build merged effective work-item context from work item, comments, and pipeline state."""

from __future__ import annotations

from typing import Any

from .ai_gen_comment_parser import filter_ai_gen_comments


def build_effective_work_item_context(
    work_item: dict,
    pipeline_state: dict | None = None,
    ai_gen_comments: list[dict] | None = None,
    approved_handoffs: list[dict] | None = None,
    max_chars: int = 16000,
    team_comments: list[dict] | None = None,
    epic_context: dict | None = None,
    question_answers: list[dict] | None = None,
) -> dict[str, Any]:
    """Build effective context without mutating the original work item."""

    item = {
        "id": work_item.get("id") or work_item.get("work_item_id") or work_item.get("System.Id"),
        "type": str(work_item.get("type") or work_item.get("work_item_type") or work_item.get("System.WorkItemType") or "").strip(),
        "title": _text(work_item, "title", "System.Title"),
        "description": _text(work_item, "description", "System.Description"),
        "acceptance_criteria": _text(work_item, "acceptanceCriteria", "acceptance_criteria", "Microsoft.VSTS.Common.AcceptanceCriteria"),
        "tags": _tags(work_item),
    }
    parsed_comments = filter_ai_gen_comments(ai_gen_comments or [])
    seen_bodies: set[str] = set()
    clarifications = _dedupe_records([item for item in parsed_comments if item["type"] == "clarification"], seen_bodies)
    approvals = _dedupe_records([item for item in parsed_comments if item["type"] == "approval"], seen_bodies)
    handoff_comments = _dedupe_records([item for item in parsed_comments if item["type"] == "handoff"], seen_bodies)
    revision_notes = _dedupe_records([item for item in parsed_comments if item["type"] == "revision"], seen_bodies)

    pipeline_feedback = _pipeline_feedback_records(pipeline_state)
    approved_summaries = _handoff_summaries(approved_handoffs or [], handoff_comments)

    context_sources = [
        "description",
        "acceptance_criteria",
    ]
    if clarifications:
        context_sources.append("ai_gen_comments")
    if pipeline_feedback:
        context_sources.append("pipeline_feedback")
    if approved_summaries:
        context_sources.append("approved_handoffs")
    if revision_notes:
        context_sources.append("revision_notes")

    # Team comments: all ADO comments (not just [ai-gen] prefixed)
    clean_team_comments = _clean_team_comments(team_comments or [])
    if clean_team_comments:
        context_sources.append("team_comments")

    # Epic context: parent Epic title + AC for child work items
    epic_ctx = epic_context or {}
    if epic_ctx.get("title") or epic_ctx.get("acceptance_criteria"):
        context_sources.append("epic_context")

    # User answers to open questions (feeds back into next refinement)
    qa_records = _parse_question_answers(question_answers or [])
    if qa_records:
        context_sources.append("question_answers")

    core_sections = _core_sections(item)
    supplemental = {
        "handoff_summaries": [_record_line("Approved handoff", record, key="summary") for record in approved_summaries],
        "pipeline_feedback": [_record_line("Pipeline feedback", record) for record in pipeline_feedback],
        "approvals": [_record_line("Approval", record) for record in approvals],
        "clarifications": [_record_line("Clarification", record) for record in clarifications],
        "revision_notes": [_record_line("Revision", record) for record in revision_notes],
        "team_comments": [_record_line("Team comment", record) for record in clean_team_comments],
        "question_answers": [f"Q: {r['question']} → A: {r['answer']}" for r in qa_records],
    }
    if epic_ctx.get("title") or epic_ctx.get("acceptance_criteria"):
        epic_lines = []
        if epic_ctx.get("title"):
            epic_lines.append(f"Epic: {epic_ctx['title']}")
        if epic_ctx.get("acceptance_criteria"):
            epic_lines.append(f"Epic AC: {str(epic_ctx['acceptance_criteria'])[:300]}")
        supplemental["epic_context"] = epic_lines

    effective_text, warnings = _build_effective_text(core_sections, supplemental, max_chars=max_chars)

    return {
        "work_item": item,
        "clarifications": clarifications,
        "approvals": approvals,
        "handoff_summaries": approved_summaries,
        "revision_notes": revision_notes,
        "pipeline_feedback": pipeline_feedback,
        "team_comments": clean_team_comments,
        "epic_context": epic_ctx,
        "question_answers": qa_records,
        "effective_text": effective_text,
        "context_sources": context_sources,
        "warnings": warnings,
    }


def _text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _tags(work_item: dict[str, Any]) -> list[str]:
    tags = work_item.get("tags", [])
    if isinstance(tags, str):
        return [item.strip() for item in tags.split(";") if item.strip()]
    if isinstance(tags, list):
        return [str(item).strip() for item in tags if str(item).strip()]
    return []


def _dedupe_records(records: list[dict[str, Any]], seen_bodies: set[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: str(item.get("created_at") or item.get("timestamp") or "")):
        body = str(record.get("body", "")).strip()
        if not body:
            continue
        key = body.lower()
        if key in seen_bodies:
            continue
        seen_bodies.add(key)
        output.append(record)
    return output


def _pipeline_feedback_records(pipeline_state: dict[str, Any] | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if not isinstance(pipeline_state, dict):
        return output
    stages = pipeline_state.get("stages", {})
    if not isinstance(stages, dict):
        return output
    for stage_name, stage_state in stages.items():
        if not isinstance(stage_state, dict):
            continue
        for feedback in stage_state.get("review_feedback", []) or []:
            if not isinstance(feedback, dict):
                continue
            comment = str(feedback.get("comment", "")).strip()
            if comment:
                output.append(
                    {
                        "type": "feedback",
                        "stage": stage_name,
                        "author": feedback.get("author"),
                        "timestamp": feedback.get("timestamp"),
                        "body": comment,
                    }
                )
        for finding in stage_state.get("unresolved_findings", []) or []:
            if not isinstance(finding, dict):
                continue
            message = str(finding.get("message", "")).strip()
            if message:
                output.append(
                    {
                        "type": "finding",
                        "stage": stage_name,
                        "severity": finding.get("severity"),
                        "timestamp": stage_state.get("updated_at") or pipeline_state.get("updated_at"),
                        "body": message,
                    }
                )
    return sorted(output, key=lambda item: str(item.get("timestamp") or ""))


def _handoff_summaries(approved_handoffs: list[dict[str, Any]], handoff_comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for handoff in approved_handoffs:
        if not isinstance(handoff, dict):
            continue
        if str(handoff.get("status", "")).lower() != "approved":
            continue
        summary = str(handoff.get("summary", "")).strip()
        if not summary:
            continue
        output.append(
            {
                "handoff_id": handoff.get("handoff_id"),
                "stage": handoff.get("stage"),
                "summary": summary,
                "approved_at": handoff.get("approved_at") or handoff.get("created_at"),
            }
        )
    for comment in handoff_comments:
        if comment.get("handoff_id") and not any(item.get("handoff_id") == comment.get("handoff_id") for item in output):
            body = str(comment.get("body", "")).strip()
            if body:
                output.append(
                    {
                        "handoff_id": comment.get("handoff_id"),
                        "stage": comment.get("stage"),
                        "summary": body,
                        "approved_at": comment.get("created_at"),
                    }
                )
    return sorted(output, key=lambda item: str(item.get("approved_at") or ""))


def _core_sections(item: dict[str, Any]) -> list[str]:
    sections = [f"Title:\n{item['title']}".strip()]
    if item["description"]:
        sections.append(f"Description:\n{item['description']}")
    if item["acceptance_criteria"]:
        sections.append(f"Acceptance Criteria:\n{item['acceptance_criteria']}")
    if item["tags"]:
        sections.append(f"Tags:\n{', '.join(item['tags'])}")
    return [section for section in sections if section.strip()]


def _record_line(label: str, record: dict[str, Any], key: str = "body") -> str:
    body = str(record.get(key, "")).strip()
    if not body:
        return ""
    stage = str(record.get("stage", "")).strip()
    prefix = f"{label} ({stage})" if stage and stage != "unknown" else label
    return f"{prefix}: {body}"


def _build_effective_text(core_sections: list[str], supplemental: dict[str, list[str]], max_chars: int) -> tuple[str, list[str]]:
    warnings: list[str] = []
    current = list(core_sections)
    optional_order = [
        ("handoff_summaries", "Approved Handoffs"),
        ("epic_context", "Epic Context"),
        ("question_answers", "Question Answers"),
        ("team_comments", "Team Comments"),
        ("pipeline_feedback", "Pipeline Feedback"),
        ("approvals", "Approvals"),
        ("clarifications", "Clarifications"),
        ("revision_notes", "Revision Notes"),
    ]
    for key, title in optional_order:
        values = [value for value in supplemental.get(key, []) if value]
        if values:
            current.append(f"{title}:\n" + "\n".join(f"- {value}" for value in values))
    while len("\n\n".join(current)) > max_chars:
        dropped = False
        for key, title in optional_order:
            values = supplemental.get(key, [])
            if values:
                values.pop(0)
                current = list(core_sections)
                for inner_key, inner_title in optional_order:
                    inner_values = [value for value in supplemental.get(inner_key, []) if value]
                    if inner_values:
                        current.append(f"{inner_title}:\n" + "\n".join(f"- {value}" for value in inner_values))
                warnings.append(f"Truncated older {key.replace('_', ' ')} to fit effective context limit.")
                dropped = True
                break
        if not dropped:
            break
    return "\n\n".join(current), _dedupe_list(warnings)


def _dedupe_list(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _clean_team_comments(raw_comments: list[dict]) -> list[dict]:
    """Return all team comments, stripping [ai-gen] metadata but preserving human text."""
    output: list[dict] = []
    seen: set[str] = set()
    for comment in raw_comments:
        body = str(comment.get("body") or comment.get("text") or "").strip()
        # Remove [ai-gen] lines from mixed comments
        clean_lines = [
            line for line in body.splitlines()
            if not line.strip().lower().startswith("[ai-gen]")
            and not line.strip().lower().startswith("handoff:")
        ]
        clean = "\n".join(clean_lines).strip()
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        output.append({
            "body": clean,
            "author": comment.get("author") or comment.get("created_by"),
            "created_at": comment.get("created_at") or comment.get("timestamp"),
        })
    return output


def _parse_question_answers(qa_list: list[dict]) -> list[dict]:
    """Normalise question/answer pairs from pipeline state."""
    output: list[dict] = []
    for item in qa_list:
        question = str(item.get("question") or item.get("q") or "").strip()
        answer = str(item.get("answer") or item.get("a") or "").strip()
        if question and answer:
            output.append({"question": question, "answer": answer})
    return output
