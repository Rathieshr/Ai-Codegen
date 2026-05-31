"""Development-planning stage for the structured assistant pipeline."""

from __future__ import annotations

from typing import Any

from context_builder.execution_packets import build_execution_packet, select_execution_files


def run_dev_assistant(
    ba_output: dict,
    ui_output: dict | None,
    repo_context: dict | None = None,
    refinement: dict | None = None,
    review_context: dict | None = None,
) -> dict:
    """Build an executor-agnostic development packet from approved upstream artifacts."""

    repo_context = repo_context or {}
    refinement = refinement or {}
    review_context = review_context or {}
    flow = _first(ba_output.get("flows", [])) or _first(refinement.get("base_flows", [])) or refinement.get("refined_base_flow") or refinement.get("base_flow")
    variant = _first(ba_output.get("variants", [])) or ba_output.get("variant") or _first(refinement.get("variants", [])) or refinement.get("refined_variant") or refinement.get("variant")
    surface = _first(refinement.get("surfaces", [])) or refinement.get("refined_surface") or refinement.get("surface") or _infer_surface(ui_output)
    scope = _build_scope(ba_output, ui_output, refinement, review_context)
    constraints = _build_constraints(ba_output, flow, review_context)
    likely_breakpoints = list(repo_context.get("likely_bug_hotspots", []))[:3]
    selected_files = _select_files(repo_context, flow)
    related_flows = list(repo_context.get("related_flows", []))
    query = _task_summary(ba_output)
    execution_packet = build_execution_packet(
        query=query,
        selected_files=selected_files,
        detected_flow=flow,
        related_flows=related_flows,
        constraints=constraints,
        likely_bug_hotspots=likely_breakpoints,
        refined_metadata={
            "base_flow": flow,
            "base_flows": _dedupe(list(refinement.get("base_flows", [])) + ([flow] if flow else [])),
            "variant": variant,
            "variants": _dedupe(list(refinement.get("variants", [])) + ([variant] if variant else [])),
            "surface": surface,
            "surfaces": _dedupe(list(refinement.get("surfaces", [])) + ([surface] if surface else [])),
            "fields": _field_names(ui_output),
            "validations": _field_validations(ui_output, refinement),
            "first_pass_scope": scope,
            "scope_hints": scope,
            "unknowns": _stage_unknowns(),
            "focus_rules": _focus_rules(flow, surface),
        },
    )
    reason = {
        "known": _dedupe([query, flow or "", surface or ""]),
        "missing": list(ba_output.get("unknowns", []))[:4],
        "goal": "Turn the approved requirement into a small, safe implementation packet.",
    }
    act = {
        "scope": scope,
        "selected_files_count": len(selected_files),
        "constraint_count": len(constraints),
    }
    observe = {
        "repo_context_available": _has_actionable_repo_context(repo_context),
        "breakpoints_found": len(likely_breakpoints),
        "ui_context_used": bool(ui_output and not ui_output.get("skippable")),
    }
    return {
        "assistant": "dev",
        "task_summary": query,
        "flow": flow,
        "variant": variant,
        "surface": surface,
        "flows": _dedupe(list(ba_output.get("flows", [])) + ([flow] if flow else [])),
        "variants": _dedupe(list(ba_output.get("variants", [])) + ([variant] if variant else [])),
        "surfaces": _dedupe(list(refinement.get("surfaces", [])) + ([surface] if surface else [])),
        "scope": scope,
        "constraints": constraints,
        "likely_breakpoints": likely_breakpoints,
        "selected_files": selected_files,
        "execution_packet": execution_packet,
        "react": {
            "reason": reason,
            "act": act,
            "observe": observe,
            "decision": "ready_for_approval" if execution_packet else "needs_revision",
        },
    }


def _build_scope(ba_output: dict, ui_output: dict | None, refinement: dict, review_context: dict) -> list[str]:
    scope = list(refinement.get("refined_scope", [])) or list(refinement.get("first_pass_scope", []))
    previous_output = review_context.get("previous_output", {})
    if not scope and isinstance(previous_output, dict):
        scope.extend(previous_output.get("scope", [])[:4])
    if ui_output and not ui_output.get("skippable"):
        if ui_output.get("screen_name"):
            scope.append(ui_output["screen_name"])
        scope.extend(ui_output.get("actions", [])[:2])
    if not scope:
        scope.extend(ba_output.get("acceptance_criteria", [])[:3])
    scope.extend(str(item.get("comment", "")).strip() for item in review_context.get("review_feedback", []))
    return _dedupe(scope)[:6]


def _build_constraints(ba_output: dict, flow: str | None, review_context: dict) -> list[str]:
    constraints = list(ba_output.get("business_rules", []))
    if flow in {"login", "signup", "session"}:
        constraints.extend(
            [
                "Do not bypass credential validation.",
                "Reuse the existing token or session generation path.",
            ]
        )
    if flow == "payment":
        constraints.append("Do not mark payment as successful before verification completes.")
    constraints.extend(str(item.get("message", "")).strip() for item in review_context.get("critic_findings", []) if item.get("severity") == "blocking")
    return _dedupe(constraints)[:6]


def _select_files(repo_context: dict, flow: str | None) -> list[str]:
    current_file = repo_context.get("session_bias_summary", {}).get("current_file") if repo_context else None
    open_files = list(repo_context.get("open_files", []))
    selected_execution_files = list(repo_context.get("selected_execution_files", []))
    if not open_files and repo_context.get("session"):
        open_files = list(repo_context["session"].get("open_files", []))
    hotspots = list(repo_context.get("likely_bug_hotspots", []))
    selected = select_execution_files(
        current_file=current_file,
        open_files=open_files,
        likely_bug_hotspots=hotspots,
        detected_flow=flow,
        max_files=4,
    )
    for path in selected_execution_files:
        if len(selected) >= 4:
            break
        if path not in selected:
            selected.append(path)
    if selected:
        return selected
    file_index = list(repo_context.get("file_index", []))
    for record in file_index:
        if flow and record.get("flow") == flow and record.get("path"):
            selected.append(record["path"])
        if len(selected) >= 4:
            break
    return _dedupe(selected)[:4]


def _field_names(ui_output: dict | None) -> list[str]:
    if not ui_output:
        return []
    return [field.get("name", "") for field in ui_output.get("fields", []) if field.get("name")]


def _field_validations(ui_output: dict | None, refinement: dict) -> list[str]:
    validations = list(refinement.get("refined_validations", [])) or list(refinement.get("validations", []))
    if not validations and ui_output:
        for field in ui_output.get("fields", []):
            validations.extend(field.get("validation", []))
    return _dedupe(validations)[:6]


def _infer_surface(ui_output: dict | None) -> str | None:
    if not ui_output or ui_output.get("skippable"):
        return None
    screen_type = ui_output.get("screen_type")
    return f"ui_{screen_type}" if screen_type and screen_type != "unknown" else "ui_screen"


def _focus_rules(flow: str | None, surface: str | None) -> list[str]:
    rules = ["Prefer the smallest safe change."]
    if surface and surface.startswith("ui"):
        rules.append("Start with the UI or input handling path before widening to deeper services.")
    if flow in {"login", "signup", "session"}:
        rules.append("Preserve the existing auth and session safety rules.")
    return _dedupe(rules)


def _first(values: list[str]) -> str:
    for value in values:
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _stage_unknowns() -> list[str]:
    return []


def _task_summary(ba_output: dict) -> str:
    raw = str(ba_output.get("refined_requirement", "")).strip()
    if not raw:
        return "Implement the approved change."
    marker = " review clarifications:"
    lowered = raw.lower()
    index = lowered.find(marker)
    if index >= 0:
        cleaned = raw[:index].rstrip(" .")
        if cleaned:
            return f"{cleaned}."
    return raw


def _has_actionable_repo_context(repo_context: dict) -> bool:
    if not repo_context:
        return False
    if repo_context.get("selected_execution_files"):
        return True
    if repo_context.get("open_files"):
        return True
    if repo_context.get("likely_bug_hotspots"):
        return True
    if repo_context.get("file_index"):
        return True
    current_file = repo_context.get("session_bias_summary", {}).get("current_file")
    return bool(current_file)
