"""UI prompt builder — produced after BA stage is approved (SDLC step 1).

The UI prompt is handed to the designer / PO to review the interface
specification before any implementation begins. Once approved, the dev
prompt is generated.

Output structure (Copilot-ready markdown prompt):
  ## Context
  ## Screen Specification
  ## Component Breakdown
  ## State & Validation Rules
  ## Acceptance Criteria (UI-specific)
  ## Do Not
"""

from __future__ import annotations

from typing import Any


def build_ui_prompt(
    ba_output: dict[str, Any],
    ui_output: dict[str, Any] | None = None,
    work_item: dict[str, Any] | None = None,
    epic_context: dict[str, Any] | None = None,
) -> str:
    """Build a UI design prompt from approved BA output.

    Called immediately after the BA stage is approved.
    UI output is optional — if already available it is merged in.

    Parameters
    ----------
    ba_output:
        Approved BA stage output dict.
    ui_output:
        Optional UI assistant output (may not yet exist at BA approval time).
    work_item:
        Original ADO work item for title/type context.
    epic_context:
        Parent epic context (title, description, AC) for grounding.

    Returns
    -------
    Copilot-ready UI specification prompt string.
    """
    wi = work_item or {}
    ui = ui_output or {}
    epic = epic_context or {}

    title = str(wi.get("title") or ba_output.get("refined_requirement") or "").strip()
    work_item_type = str(wi.get("type") or "Story").strip()
    flows = ba_output.get("flows") or []
    actors = ba_output.get("actors") or []
    variant = ba_output.get("variant") or ""
    business_rules = ba_output.get("business_rules") or []
    ac = ba_output.get("acceptance_criteria") or []
    unknowns = [q for q in (ba_output.get("unknowns") or []) if q]

    # UI-specific fields from ui_output (if already generated)
    screen_type = str(ui.get("screen_type") or "screen").strip()
    fields: list[dict] = ui.get("fields") or []
    surfaces: list[str] = ui.get("surfaces") or []
    navigation = ui.get("navigation") or {}
    states = ui.get("states") or []

    # Epic grounding
    epic_title = str(epic.get("title") or "").strip()
    epic_ac = str(epic.get("acceptance_criteria") or "").strip()

    parts: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    parts.append(f"# UI Specification Prompt: {title}")
    parts.append(f"**Work Item Type:** {work_item_type}  |  **Variant:** {variant or 'Standard'}\n")

    # ── Epic grounding ────────────────────────────────────────────────────────
    if epic_title:
        parts.append("## Parent Epic Context")
        parts.append(f"**Epic:** {epic_title}")
        if epic_ac:
            parts.append(f"**Epic AC:** {epic_ac[:300]}")
        parts.append("")

    # ── Context ───────────────────────────────────────────────────────────────
    parts.append("## Context")
    if actors:
        parts.append(f"**Actors:** {', '.join(str(a) for a in actors)}")
    if flows:
        parts.append(f"**User Flows:** {', '.join(str(f) for f in flows)}")
    parts.append("")

    # ── Screen Specification ──────────────────────────────────────────────────
    parts.append("## Screen Specification")
    parts.append(f"**Screen Type:** {screen_type.replace('_', ' ').title()}")
    if surfaces:
        parts.append(f"**Surfaces:** {', '.join(surfaces)}")
    parts.append("")

    # ── Component Breakdown ───────────────────────────────────────────────────
    parts.append("## Component Breakdown")
    if fields:
        parts.append("**Form Fields:**")
        for field in fields:
            name = str(field.get("name") or "").strip()
            field_type = str(field.get("type") or "text").strip()
            required = "required" if field.get("required") else "optional"
            validation = str(field.get("validation") or "").strip()
            line = f"- `{name}` ({field_type}, {required})"
            if validation:
                line += f" — validation: {validation}"
            parts.append(line)
    else:
        # Generate generic components based on flow
        flow_str = " | ".join(str(f) for f in flows[:3])
        parts.append(f"Design components for the following flows: {flow_str or title}")
        parts.append("Include: primary action button, error state, success state, loading indicator.")
    parts.append("")

    # ── State & Validation Rules ──────────────────────────────────────────────
    parts.append("## State & Validation Rules")
    if states:
        for state in states[:6]:
            parts.append(f"- {state}")
    if business_rules:
        parts.append("**Business Rules:**")
        for rule in business_rules[:6]:
            parts.append(f"- {rule}")
    if navigation:
        parts.append(f"**Navigation:** {_format_navigation(navigation)}")
    parts.append("")

    # ── Acceptance Criteria ────────────────────────────────────────────────────
    parts.append("## Acceptance Criteria (UI)")
    if ac:
        for item in (ac if isinstance(ac, list) else [ac])[:8]:
            parts.append(f"- {item}")
    else:
        parts.append(f"- UI correctly supports all flows: {', '.join(str(f) for f in flows)}")
        parts.append("- All form validations are displayed inline.")
        parts.append("- Loading and error states are handled visually.")
    parts.append("")

    # ── Open Questions ────────────────────────────────────────────────────────
    if unknowns:
        parts.append("## Open Questions (Answer before implementation)")
        for q in unknowns[:4]:
            parts.append(f"- [ ] {q}")
        parts.append("")

    # ── Constraints ───────────────────────────────────────────────────────────
    parts.append("## Do Not")
    parts.append("- Do not implement backend logic or API calls in this prompt.")
    parts.append("- Do not skip error states or loading spinners.")
    parts.append("- Do not proceed to coding prompt until this UI spec is approved by the PO/designer.")
    parts.append("")
    parts.append("---")
    parts.append("*Generated by ai-gen UI Prompt Builder. Approve this spec before generating the Coding Prompt.*")

    return "\n".join(parts)


def _format_navigation(nav: dict | list | str) -> str:
    if isinstance(nav, str):
        return nav
    if isinstance(nav, list):
        return " → ".join(str(item) for item in nav[:5])
    if isinstance(nav, dict):
        items = []
        for key, val in list(nav.items())[:4]:
            items.append(f"{key}: {val}")
        return ", ".join(items)
    return str(nav)
