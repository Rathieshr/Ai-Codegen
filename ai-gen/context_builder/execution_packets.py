"""Compact final prompt packets for execution/respond/explore handoff."""

from __future__ import annotations

from typing import Any


def select_execution_files(
    current_file: str | None,
    open_files: list[str],
    likely_bug_hotspots: list | None,
    detected_flow: str | None,
    max_files: int = 4,
) -> list[str]:
    """Select a compact file scope, prioritizing current file and hotspots."""

    selected: list[str] = []
    _append_path(selected, current_file)
    for hotspot in likely_bug_hotspots or []:
        _append_path(selected, hotspot.get("file"))
    flow = (detected_flow or "").lower()
    for path in open_files:
        normalized = path.lower()
        if flow and flow in normalized:
            _append_path(selected, path)
    for path in open_files:
        _append_path(selected, path)
    return selected[:max_files]


def build_execution_packet(
    query: str,
    selected_files: list[str],
    detected_flow: str | None,
    related_flows: list[str],
    constraints: list[str],
    likely_bug_hotspots: list[dict[str, Any]],
) -> str:
    """Build a compact no-replan/no-rescan implementation handoff."""

    sections = [
        "# Task",
        query.strip(),
        _scope_section(selected_files, detected_flow, related_flows),
        _constraints_section(constraints),
        _breakpoints_section(likely_bug_hotspots),
        "# Execution Rules",
        "\n".join(
            [
                "- Do not repeat broad repo analysis unless necessary.",
                "- Use the provided scope, constraints, and likely breakpoints first.",
                "- Do not widen scope unless the listed path fails to explain the task.",
                "- Avoid re-planning from scratch.",
                "- Apply the smallest safe change.",
            ]
        ),
    ]
    return "\n\n".join(section for section in sections if section).strip()


def build_response_packet(
    query: str,
    detected_flow: str | None,
    related_flows: list[str],
    constraints: list[str],
) -> str:
    """Build a concise answer-oriented prompt for local/respond tasks."""

    context_lines: list[str] = []
    if detected_flow:
        context_lines.append(f"- Flow: {detected_flow}")
    if related_flows:
        context_lines.append(f"- Related: {', '.join(_dedupe(related_flows))}")
    for constraint in constraints[:3]:
        context_lines.append(f"- Constraint: {constraint}")

    return "\n\n".join(
        section
        for section in [
            f"Task: {query.strip()}",
            "Context:\n" + "\n".join(context_lines) if context_lines else "",
            "Instructions:\n- Explain the business flow simply.\n- Focus on structure, not implementation detail.\n- Keep answer concise.",
        ]
        if section
    ).strip()


def build_exploration_packet(
    query: str,
    detected_flow: str | None,
    related_flows: list[str],
    constraints: list[str],
) -> str:
    """Build a structured prompt for low-confidence exploration."""

    return "\n\n".join(
        section
        for section in [
            "# Exploration Task",
            query.strip(),
            _scope_section([], detected_flow, related_flows),
            _constraints_section(constraints[:4]),
            "# Instructions",
            "\n".join(
                [
                    "- Inspect the relevant repo areas before changing code.",
                    "- Identify the smallest credible scope.",
                    "- Preserve listed constraints.",
                    "- Ask for clarification if the task remains ambiguous.",
                ]
            ),
        ]
        if section
    ).strip()


def _scope_section(selected_files: list[str], detected_flow: str | None, related_flows: list[str]) -> str:
    lines = ["# Scope"]
    if selected_files:
        lines.append("Files:")
        lines.extend(f"- {path}" for path in selected_files)
    if detected_flow:
        lines.append(f"Flow:\n- {detected_flow}")
    if related_flows:
        lines.append("Related:")
        lines.extend(f"- {flow}" for flow in _dedupe(related_flows))
    return "\n".join(lines) if len(lines) > 1 else ""


def _constraints_section(constraints: list[str]) -> str:
    if not constraints:
        return ""
    lines = ["# Constraints"]
    lines.extend(f"- {constraint}" for constraint in _dedupe(constraints)[:4])
    return "\n".join(lines)


def _breakpoints_section(hotspots: list[dict[str, Any]]) -> str:
    if not hotspots:
        return ""
    lines = ["# Likely Breakpoints"]
    for hotspot in hotspots[:3]:
        label = f"{hotspot.get('flow', 'unknown')}/{hotspot.get('role', 'unknown')}"
        reasons = ", ".join(hotspot.get("reasons", [])[:3])
        lines.append(f"- {hotspot.get('file')} ({label}): {reasons}")
    return "\n".join(lines)


def _append_path(values: list[str], path: str | None) -> None:
    normalized = (path or "").replace("\\", "/").strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output
