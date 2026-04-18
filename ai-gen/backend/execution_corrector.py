"""Deterministic retry planning for failed execution validation."""

from __future__ import annotations

from typing import Any

from context_builder.execution_packets import build_execution_packet


def generate_retry_plan(
    validation_result: dict[str, Any],
    original_execution_context: dict[str, Any],
    selected_files: list[str],
    detected_flow: str | None,
    related_flows: list[str],
) -> dict[str, Any]:
    """Generate a tighter retry plan after validation detects execution issues."""

    violations = validation_result.get("constraint_violations", []) or []
    out_of_scope = validation_result.get("out_of_scope_files", []) or []
    risky = validation_result.get("risky_changes", []) or []

    if not out_of_scope and not violations and not risky:
        return {
            "retry_required": False,
            "reason": "no validation issues detected",
            "corrected_files": _dedupe(selected_files),
            "reinforced_constraints": _dedupe(original_execution_context.get("constraints", [])),
            "adjusted_instructions": [],
            "strategy": "none",
        }

    strategy = _strategy(out_of_scope, violations, risky)
    reason = _reason(out_of_scope, violations, risky)
    corrected_files = _corrected_files(
        selected_files=selected_files,
        likely_breakpoints=original_execution_context.get("likely_breakpoints", []),
        out_of_scope=out_of_scope,
    )
    reinforced_constraints = _reinforced_constraints(
        original_execution_context.get("constraints", []),
        violations,
    )
    adjusted_instructions = _adjusted_instructions(out_of_scope, violations, risky)

    return {
        "retry_required": True,
        "reason": reason,
        "corrected_files": corrected_files,
        "reinforced_constraints": reinforced_constraints,
        "adjusted_instructions": adjusted_instructions,
        "strategy": strategy,
    }


def build_corrected_execution_prompt(
    query: str,
    retry_plan: dict[str, Any],
    detected_flow: str | None,
    related_flows: list[str],
    previous_issues: list[str],
) -> str:
    """Build a corrected retry prompt using the existing execution packet style."""

    if not retry_plan.get("retry_required"):
        return ""

    packet = build_execution_packet(
        query=f"{query.strip()} (retry)",
        selected_files=retry_plan.get("corrected_files", []),
        detected_flow=detected_flow,
        related_flows=related_flows,
        constraints=retry_plan.get("reinforced_constraints", []),
        likely_bug_hotspots=[],
    )
    return "\n\n".join(
        section
        for section in [
            packet.replace("# Constraints", "# Constraints (Reinforced)"),
            _previous_issues_section(previous_issues),
            "# Retry Instructions\n"
            + "\n".join(f"- {instruction}" for instruction in retry_plan.get("adjusted_instructions", [])),
        ]
        if section.strip()
    )


def _strategy(out_of_scope: list[str], violations: list[str], risky: list[str]) -> str:
    if out_of_scope:
        return "narrow_scope"
    if violations:
        return "constraint_enforcement"
    if risky:
        return "focus_breakpoints"
    return "none"


def _reason(out_of_scope: list[str], violations: list[str], risky: list[str]) -> str:
    if out_of_scope:
        return "scope drift detected"
    if violations:
        return "constraint violation detected"
    if risky:
        return "risky changes detected"
    return "no validation issues detected"


def _corrected_files(selected_files: list[str], likely_breakpoints: list[str], out_of_scope: list[str]) -> list[str]:
    blocked = set(out_of_scope)
    candidates = [path for path in selected_files if path not in blocked]
    for path in likely_breakpoints:
        if path not in blocked:
            candidates.append(path)
    return _dedupe(candidates)[:4]


def _reinforced_constraints(constraints: list[str], violations: list[str]) -> list[str]:
    reinforced: list[str] = []
    for violation in violations:
        reinforced.append(f"Previous attempt violated constraint: {violation}")
    reinforced.extend(constraints)
    return _dedupe(reinforced)


def _adjusted_instructions(out_of_scope: list[str], violations: list[str], risky: list[str]) -> list[str]:
    instructions = [
        "Do not repeat previous mistakes.",
        "Strictly follow the corrected file scope.",
        "Apply the smallest safe fix.",
    ]
    if out_of_scope:
        instructions.append("Do not modify files outside this list.")
    if violations:
        instructions.append("Treat reinforced constraints as non-negotiable.")
    if risky:
        instructions.append("Avoid touching auth/payment/session unless necessary.")
    return _dedupe(instructions)


def _previous_issues_section(previous_issues: list[str]) -> str:
    issues = _dedupe(previous_issues)
    if not issues:
        return ""
    lines = ["# Previous Issues"]
    lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines)


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output
