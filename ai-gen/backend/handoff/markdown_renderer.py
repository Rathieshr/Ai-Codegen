"""Render handoff artifacts into readable markdown."""

from __future__ import annotations

import json


def render_handoff_markdown(handoff: dict) -> str:
    """Render a handoff artifact as human-readable markdown."""

    sections = [
        f"# {handoff.get('stage', 'stage').upper()} Handoff",
        f"Status: {handoff.get('status', 'draft')}",
        "",
        "## Summary",
        handoff.get("summary", "No summary provided."),
        "",
        "## Stage Output",
        "```json",
        json.dumps(handoff.get("content", {}), indent=2, ensure_ascii=True),
        "```",
    ]
    if handoff.get("constraints"):
        sections.extend(["", "## Constraints"])
        sections.extend(f"- {item}" for item in handoff["constraints"])
    if handoff.get("open_questions"):
        sections.extend(["", "## Open Questions"])
        sections.extend(f"- {item}" for item in handoff["open_questions"])
    if handoff.get("next_actions"):
        sections.extend(["", "## Next Actions"])
        sections.extend(f"- {item}" for item in handoff["next_actions"])
    if handoff.get("refinement"):
        sections.extend(["", "## Refinement", "```json", json.dumps(handoff["refinement"], indent=2, ensure_ascii=True), "```"])
    if handoff.get("repo_context"):
        sections.extend(["", "## Repo Context", "```json", json.dumps(handoff["repo_context"], indent=2, ensure_ascii=True), "```"])
    return "\n".join(sections).strip() + "\n"
