"""Deterministic MVP planner for risky or multi-step ai-gen tasks."""

from __future__ import annotations

from typing import Any


ANALYSIS_KEYWORDS = (
    "explain",
    "summarize",
    "understand",
    "what does",
    "what is",
    "describe",
)

PLAN_KEYWORDS = (
    "add",
    "build",
    "create",
    "implement",
    "modify",
    "generate",
    "otp",
    "retry",
    "payment",
    "transaction",
    "session",
    "auth",
    "login",
    "architecture",
    "re-architect",
    "cross-platform",
    "migration",
    "migrate",
    "refactor",
)

ACTION_PLAN_KEYWORDS = (
    "add",
    "build",
    "create",
    "implement",
    "modify",
    "generate",
    "retry",
    "migrate",
    "migration",
    "refactor",
    "re-architect",
)

RISKY_DOMAINS = ("auth", "login", "password", "token", "otp", "payment", "transaction", "session")


def should_plan(query: str, intent: str | None = None) -> bool:
    """Return whether a task is likely multi-step or risky enough to plan."""

    normalized = _normalize(query)
    if _contains_any(normalized, ANALYSIS_KEYWORDS) and not _contains_any(normalized, ACTION_PLAN_KEYWORDS):
        return False

    if intent == "refactor":
        return True
    if intent == "feature" and _contains_any(normalized, PLAN_KEYWORDS):
        return True
    if intent == "bug_fix" and _contains_any(normalized, RISKY_DOMAINS):
        return True

    return _contains_any(normalized, PLAN_KEYWORDS)


def create_plan(
    query: str,
    intent: str | None = None,
    linked_flows: list[str] | None = None,
    impacted_components: list[str] | None = None,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    """Create a short, normalized execution plan for Codex prompt guidance."""

    linked_flows = linked_flows or []
    impacted_components = impacted_components or []
    constraints = constraints or []
    normalized = _normalize(query)

    needs_planning = should_plan(query, intent)
    if intent in {"feature", "bug_fix", "refactor"} and (linked_flows or constraints):
        needs_planning = True
    if intent == "refactor" and len(impacted_components) > 1:
        needs_planning = True

    if not needs_planning:
        return {"needs_planning": False, "plan_type": "none", "steps": []}

    if intent == "bug_fix" and not _contains_any(normalized, ("migration", "migrate", "cross-platform", "architecture", "refactor")):
        return {
            "needs_planning": True,
            "plan_type": "bug_fix",
            "steps": _bug_fix_plan_steps(),
        }

    plan_type = _plan_type(normalized, intent)
    if _is_auth_or_otp_task(normalized, linked_flows, constraints):
        steps = _auth_plan_steps()
    elif _contains_any(normalized, ("payment", "transaction", "gateway", "checkout", "retry")):
        steps = _payment_plan_steps()
    elif plan_type == "migration":
        steps = _migration_plan_steps()
    elif plan_type == "refactor":
        steps = _refactor_plan_steps()
    else:
        steps = _implementation_plan_steps()

    return {
        "needs_planning": True,
        "plan_type": plan_type,
        "steps": steps,
    }


def summarize_plan(plan: dict[str, Any]) -> str:
    """Return a compact summary for API consumers and previews."""

    if not plan.get("needs_planning"):
        return "Planning not required."

    steps = plan.get("steps", [])
    risks = [step.get("risk", "low") for step in steps]
    highest_risk = "high" if "high" in risks else "medium" if "medium" in risks else "low"
    return f"{plan.get('plan_type', 'implementation')} plan with {len(steps)} steps; highest risk: {highest_risk}."


def _auth_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "id": "step_1",
            "title": "Analyze existing login and session flow",
            "purpose": "Identify the correct insertion point for OTP without creating a second auth model.",
            "risk": "medium",
        },
        {
            "id": "step_2",
            "title": "Add OTP validation in the existing authentication sequence",
            "purpose": "Extend login safely while preserving credential validation order.",
            "risk": "high",
        },
        {
            "id": "step_3",
            "title": "Reuse existing token or session generation path",
            "purpose": "Avoid duplicate session logic and preserve existing constraints.",
            "risk": "high",
        },
        {
            "id": "step_4",
            "title": "Verify impacted flows and constraints before finalizing",
            "purpose": "Ensure auth constraints and linked flow behavior remain valid.",
            "risk": "medium",
        },
    ]


def _payment_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "id": "step_1",
            "title": "Analyze existing payment and transaction flow",
            "purpose": "Find the correct retry or validation point without bypassing gateway verification.",
            "risk": "medium",
        },
        {
            "id": "step_2",
            "title": "Apply the payment change after required validation",
            "purpose": "Preserve fraud checks, gateway state, and transaction status ordering.",
            "risk": "high",
        },
        {
            "id": "step_3",
            "title": "Preserve transaction persistence",
            "purpose": "Ensure successful and failed attempts continue to write required records.",
            "risk": "high",
        },
        {
            "id": "step_4",
            "title": "Verify payment constraints and affected components",
            "purpose": "Confirm the change does not mark payment success too early.",
            "risk": "medium",
        },
    ]


def _migration_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "id": "step_1",
            "title": "Map existing flows and dependent components",
            "purpose": "Identify behavior that must survive the migration.",
            "risk": "medium",
        },
        {
            "id": "step_2",
            "title": "Migrate the smallest coherent slice first",
            "purpose": "Reduce blast radius while preserving existing contracts.",
            "risk": "high",
        },
        {
            "id": "step_3",
            "title": "Keep compatibility paths until verification passes",
            "purpose": "Avoid breaking callers during the migration.",
            "risk": "high",
        },
        {
            "id": "step_4",
            "title": "Verify impacted flows and constraints",
            "purpose": "Confirm linked flows and architecture relationships still behave correctly.",
            "risk": "medium",
        },
    ]


def _refactor_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "id": "step_1",
            "title": "Analyze current structure and dependencies",
            "purpose": "Identify boundaries that should remain stable during the refactor.",
            "risk": "medium",
        },
        {
            "id": "step_2",
            "title": "Refactor one behavior-preserving slice",
            "purpose": "Improve structure without changing business logic.",
            "risk": "medium",
        },
        {
            "id": "step_3",
            "title": "Reuse existing services and flow contracts",
            "purpose": "Avoid duplicate implementations or accidental architecture drift.",
            "risk": "high",
        },
        {
            "id": "step_4",
            "title": "Verify impacted components before finalizing",
            "purpose": "Ensure the refactor did not change critical behavior.",
            "risk": "medium",
        },
    ]


def _implementation_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "id": "step_1",
            "title": "Inspect the relevant existing flow",
            "purpose": "Find the safest insertion point for the requested change.",
            "risk": "medium",
        },
        {
            "id": "step_2",
            "title": "Implement the smallest safe change",
            "purpose": "Satisfy the task while preserving current business logic.",
            "risk": "medium",
        },
        {
            "id": "step_3",
            "title": "Reuse existing components and dependencies",
            "purpose": "Avoid duplicate services, models, or flow branches.",
            "risk": "medium",
        },
        {
            "id": "step_4",
            "title": "Verify constraints and affected behavior",
            "purpose": "Confirm the generated change stays aligned with the provided context.",
            "risk": "medium",
        },
    ]


def _bug_fix_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "id": "step_1",
            "title": "Identify root cause in the relevant flow",
            "purpose": "Confirm the bug source before changing working behavior.",
            "risk": "medium",
        },
        {
            "id": "step_2",
            "title": "Apply the smallest safe fix without breaking constraints",
            "purpose": "Fix only the failing behavior while preserving critical safeguards.",
            "risk": "medium",
        },
    ]


def _plan_type(normalized_query: str, intent: str | None) -> str:
    if _contains_any(normalized_query, ("migrate", "migration")):
        return "migration"
    if intent == "refactor" or _contains_any(normalized_query, ("refactor", "optimize", "improve")):
        return "refactor"
    if _contains_any(normalized_query, ANALYSIS_KEYWORDS):
        return "analysis"
    return "implementation"


def _is_auth_or_otp_task(
    normalized_query: str,
    linked_flows: list[str],
    constraints: list[str],
) -> bool:
    joined_links = _normalize(" ".join(linked_flows))
    joined_constraints = _normalize(" ".join(constraints))
    return (
        _contains_any(normalized_query, RISKY_DOMAINS)
        or _contains_any(joined_links, ("login", "auth", "token", "session"))
        or _contains_any(joined_constraints, ("credential", "authentication", "token", "session", "password"))
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())
