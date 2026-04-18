"""MVP flow composition with dependency injection."""

from __future__ import annotations

from typing import Any


INJECTION_KEYWORDS = ("token", "session", "auth")
MAX_INJECTION_DEPTH = 2


def compose_flow(main_flow: list[str], dependent_flows: list[dict[str, Any]]) -> list[str]:
    """Inject dependent flow steps into the main flow at logical trigger points."""

    dependency_steps = _collect_dependency_steps(
        flows=dependent_flows,
        depth=0,
        visiting=set(),
    )

    composed_steps: list[str] = []
    seen_steps: set[str] = set()
    injected = False
    injection_keyword = _best_injection_keyword(main_flow)

    for step in main_flow:
        _append_step(composed_steps, seen_steps, step)
        if not injected and _should_inject_after(step, injection_keyword):
            for dependency_step in dependency_steps:
                _append_step(composed_steps, seen_steps, dependency_step)
            injected = True

    if not injected:
        for dependency_step in dependency_steps:
            _append_step(composed_steps, seen_steps, dependency_step)

    return composed_steps


def _collect_dependency_steps(
    flows: list[dict[str, Any]],
    depth: int,
    visiting: set[str],
) -> list[str]:
    """Collect dependency steps recursively with a small depth guard."""

    if depth >= MAX_INJECTION_DEPTH:
        return []

    collected_steps: list[str] = []
    seen_steps: set[str] = set()

    for flow in flows:
        flow_key = _flow_key(flow)
        if flow_key in visiting:
            continue

        visiting.add(flow_key)
        for step in flow.get("steps", flow.get("flow", [])):
            _append_step(collected_steps, seen_steps, step)

        nested_steps = _collect_dependency_steps(
            flows=flow.get("dependent_flows", []),
            depth=depth + 1,
            visiting=visiting,
        )
        for step in nested_steps:
            _append_step(collected_steps, seen_steps, step)
        visiting.remove(flow_key)

    return collected_steps


def _best_injection_keyword(main_flow: list[str]) -> str | None:
    """Choose the strongest injection keyword present in the main flow."""

    for keyword in INJECTION_KEYWORDS:
        if any(keyword in step.lower() for step in main_flow):
            return keyword
    return None


def _should_inject_after(step: str, injection_keyword: str | None) -> bool:
    """Return whether a main step is a logical injection point."""

    if not injection_keyword:
        return False
    normalized_step = step.lower()
    return injection_keyword in normalized_step


def _append_step(steps: list[str], seen_steps: set[str], step: str) -> None:
    """Append a normalized step once while preserving order."""

    normalized_step = step.strip()
    if not normalized_step or normalized_step in seen_steps:
        return
    seen_steps.add(normalized_step)
    steps.append(normalized_step)


def _flow_key(flow: dict[str, Any]) -> str:
    """Return a stable key for simple cycle prevention."""

    return str(flow.get("id") or flow.get("name") or id(flow))
