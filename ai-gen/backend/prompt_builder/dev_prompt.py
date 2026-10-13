"""Coding dev prompt builder — produced after UI stage is approved (SDLC step 2).

The coding prompt is handed to the developer / Copilot Chat / Cursor for
implementation. It includes the full approved UI spec, data contracts,
repo context, and task-specific constraints.

Output structure:
  ## Objective
  ## Work Item Context
  ## Approved UI Specification (reference)
  ## Implementation Scope
  ## Data Contracts & API Interfaces
  ## Selected Files (repo-aware)
  ## Acceptance Criteria
  ## Constraints & Safety Rules
  ## Task Breakdown (for complex items)
  ## Example Usage / Test Scenarios
"""

from __future__ import annotations

from typing import Any


def build_dev_prompt(
    ba_output: dict[str, Any],
    dev_output: dict[str, Any] | None = None,
    ui_output: dict[str, Any] | None = None,
    repo_context: dict[str, Any] | None = None,
    work_item: dict[str, Any] | None = None,
    epic_context: dict[str, Any] | None = None,
    test_output: dict[str, Any] | None = None,
) -> str:
    """Build a Copilot-ready coding prompt from approved BA + UI outputs.

    Called immediately after the UI stage is approved (SDLC step 2).

    Parameters
    ----------
    ba_output:
        Approved BA stage output dict.
    dev_output:
        Optional dev assistant output (execution packet, scope, constraints).
    ui_output:
        Approved UI assistant output.
    repo_context:
        Resolved repo context (branch, selected files, tech stack).
    work_item:
        Original ADO work item.
    epic_context:
        Parent epic context for grounding.
    test_output:
        Optional test checklist output to embed as test scenarios.

    Returns
    -------
    Copilot-ready coding prompt string.
    """
    wi = work_item or {}
    dev = dev_output or {}
    ui = ui_output or {}
    repo = repo_context or {}
    epic = epic_context or {}
    test = test_output or {}

    title = str(wi.get("title") or ba_output.get("refined_requirement") or "").strip()
    work_item_type = str(wi.get("type") or "Story").strip()
    work_item_id = str(wi.get("id") or wi.get("work_item_id") or "").strip()

    # BA fields
    flows = ba_output.get("flows") or []
    actors = ba_output.get("actors") or []
    variant = ba_output.get("variant") or ""
    business_rules = ba_output.get("business_rules") or []
    ac = ba_output.get("acceptance_criteria") or []

    # Dev fields
    scope = dev.get("scope") or ""
    constraints = dev.get("constraints") or []
    surfaces = dev.get("surfaces") or []
    execution_packet = str(dev.get("execution_packet") or "").strip()
    selected_files = dev.get("selected_files") or repo.get("selected_files") or []
    task_breakdown = dev.get("task_breakdown") or dev.get("proposed_child_tasks") or []

    # UI fields (approved spec summary)
    ui_fields = ui.get("fields") or []
    ui_screen_type = str(ui.get("screen_type") or "").strip()
    ui_states = ui.get("states") or []

    # Repo context
    repo_branch = str(repo.get("resolved_branch_name") or repo.get("branch") or "").strip()
    tech_stack = repo.get("tech_stack") or repo.get("technologies") or []
    api_contracts = dev.get("api_contracts") or dev.get("interfaces") or []

    # Epic
    epic_title = str(epic.get("title") or "").strip()
    epic_ac = str(epic.get("acceptance_criteria") or "").strip()

    # Test scenarios
    test_cases = test.get("test_cases") or []

    parts: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    wi_ref = f"#{work_item_id}" if work_item_id else ""
    parts.append(f"# Coding Prompt: {title} {wi_ref}".strip())
    parts.append(f"**Type:** {work_item_type}  |  **Variant:** {variant or 'Standard'}  |  **Branch:** `{repo_branch or 'feature/...'}`\n")

    # ── Epic grounding ────────────────────────────────────────────────────────
    if epic_title:
        parts.append("## Parent Epic Context")
        parts.append(f"**Epic:** {epic_title}")
        if epic_ac:
            parts.append(f"**Epic AC:** {epic_ac[:250]}")
        parts.append("")

    # ── Objective ─────────────────────────────────────────────────────────────
    parts.append("## Objective")
    refined = str(ba_output.get("refined_requirement") or title)
    parts.append(refined[:400])
    if actors:
        parts.append(f"\n**Actors:** {', '.join(str(a) for a in actors)}")
    if flows:
        parts.append(f"**Flows:** {', '.join(str(f) for f in flows)}")
    parts.append("")

    # ── Approved UI Spec (reference) ──────────────────────────────────────────
    if ui_fields or ui_screen_type:
        parts.append("## Approved UI Specification (reference — do not redesign)")
        if ui_screen_type:
            parts.append(f"**Screen Type:** {ui_screen_type.replace('_', ' ').title()}")
        if ui_fields:
            parts.append("**Fields:**")
            for field in ui_fields[:10]:
                name = str(field.get("name") or "").strip()
                ftype = str(field.get("type") or "text").strip()
                req = "required" if field.get("required") else "optional"
                parts.append(f"  - `{name}` ({ftype}, {req})")
        if ui_states:
            parts.append(f"**UI States:** {', '.join(str(s) for s in ui_states[:5])}")
        parts.append("")

    # ── Implementation Scope ──────────────────────────────────────────────────
    parts.append("## Implementation Scope")
    if scope:
        parts.append(scope[:400])
    if surfaces:
        parts.append(f"**Surfaces to implement:** {', '.join(str(s) for s in surfaces)}")
    if tech_stack:
        parts.append(f"**Tech Stack:** {', '.join(str(t) for t in tech_stack[:8])}")
    parts.append("")

    # ── Data Contracts & API ──────────────────────────────────────────────────
    if api_contracts:
        parts.append("## Data Contracts & API Interfaces")
        for contract in api_contracts[:5]:
            if isinstance(contract, str):
                parts.append(f"- {contract}")
            elif isinstance(contract, dict):
                endpoint = contract.get("endpoint") or contract.get("name") or str(contract)
                parts.append(f"- `{endpoint}`")
        parts.append("")

    # ── Selected Files ────────────────────────────────────────────────────────
    if selected_files:
        parts.append("## Files to Modify / Reference")
        for f in selected_files[:12]:
            path = str(f.get("path") or f) if isinstance(f, dict) else str(f)
            reason = str(f.get("reason") or "") if isinstance(f, dict) else ""
            line = f"- `{path}`"
            if reason:
                line += f"  — {reason}"
            parts.append(line)
        parts.append("")

    # ── Acceptance Criteria ────────────────────────────────────────────────────
    parts.append("## Acceptance Criteria")
    ac_items = ac if isinstance(ac, list) else [ac] if ac else []
    if ac_items:
        for item in ac_items[:8]:
            parts.append(f"- [ ] {item}")
    else:
        parts.append(f"- [ ] All flows implemented: {', '.join(str(f) for f in flows)}")
        parts.append("- [ ] Unit tests pass for happy path, error states, and edge cases.")
    parts.append("")

    # ── Business Rules & Constraints ──────────────────────────────────────────
    constraint_items = list(constraints) + list(business_rules)
    if constraint_items:
        parts.append("## Constraints & Safety Rules")
        for rule in constraint_items[:8]:
            parts.append(f"- {rule}")
        parts.append("")

    # ── Execution Packet ──────────────────────────────────────────────────────
    if execution_packet:
        parts.append("## Execution Packet (detailed implementation guide)")
        parts.append(f"```\n{execution_packet[:2000]}\n```")
        parts.append("")

    # ── Task Breakdown ────────────────────────────────────────────────────────
    if task_breakdown:
        parts.append("## Task Breakdown")
        for task in task_breakdown[:8]:
            if isinstance(task, dict):
                task_title = str(task.get("title") or task.get("name") or "").strip()
                if task_title:
                    parts.append(f"- [ ] {task_title}")
            elif isinstance(task, str):
                parts.append(f"- [ ] {task}")
        parts.append("")

    # ── Test Scenarios ────────────────────────────────────────────────────────
    if test_cases:
        parts.append("## Test Scenarios (from approved test plan)")
        for case in test_cases[:6]:
            if isinstance(case, dict):
                case_title = str(case.get("title") or "").strip()
                case_type = str(case.get("type") or "").strip()
                if case_title:
                    parts.append(f"- [{case_type.upper()}] {case_title}")
        parts.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    parts.append("---")
    parts.append("**Instructions for Copilot/Cursor:**")
    parts.append("1. Implement only what is in scope above. Do not add unrequested features.")
    parts.append("2. Follow the approved UI specification exactly.")
    parts.append("3. Write unit tests for all AC items.")
    parts.append("4. Do not commit directly to main — use the branch specified above.")
    parts.append("")
    parts.append("*Generated by ai-gen Coding Prompt Builder. UI approval was prerequisite.*")

    return "\n".join(parts)
