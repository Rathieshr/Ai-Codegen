"""Business-analysis stage for the structured assistant pipeline."""

from __future__ import annotations

from typing import Any


def run_ba_assistant(work_item: dict, refinement: dict | None = None) -> dict:
    """Build a deterministic BA artifact from work item text and optional refinement."""

    refinement = refinement or {}
    title = _text(work_item, "title")
    description = _text(work_item, "description")
    acceptance_text = _text(work_item, "acceptanceCriteria") or _text(work_item, "acceptance_criteria")
    tags = [str(tag).strip() for tag in work_item.get("tags", []) if str(tag).strip()]
    combined = " ".join(part for part in [title, description, acceptance_text, " ".join(tags)] if part).strip()
    variant = refinement.get("refined_variant") or refinement.get("variant")
    base_flow = refinement.get("refined_base_flow") or refinement.get("base_flow") or _detect_flow(combined)
    actors = _infer_actors(combined)
    flows = _dedupe([base_flow] if base_flow else [])
    business_rules = _business_rules(combined, refinement)
    acceptance_criteria = _parse_acceptance_criteria(acceptance_text, refinement)
    unknowns = _dedupe(
        list(refinement.get("refinement_unknowns", []))
        + list(refinement.get("unknowns", []))
        + _detect_unknowns(combined, variant)
    )
    refined_requirement = _refined_requirement(title, description, refinement)

    reason = {
        "known": _dedupe(
            [item for item in [title, f"flow:{base_flow}" if base_flow else "", f"variant:{variant}" if variant else ""] if item]
        ),
        "missing": unknowns[:4],
        "goal": "Clarify the requirement, actors, flows, and business rules before UI or development work starts.",
    }
    act = {
        "requirement": refined_requirement,
        "actors": actors,
        "flows": flows,
        "acceptance_criteria_count": len(acceptance_criteria),
    }
    observe = {
        "used_refinement": bool(refinement),
        "tags": tags,
        "surface": refinement.get("refined_surface") or refinement.get("surface"),
    }

    return {
        "assistant": "ba",
        "refined_requirement": refined_requirement,
        "actors": actors,
        "flows": flows,
        "variant": variant or None,
        "business_rules": business_rules,
        "acceptance_criteria": acceptance_criteria,
        "unknowns": unknowns,
        "react": {
            "reason": reason,
            "act": act,
            "observe": observe,
            "decision": "ready_for_approval" if refined_requirement else "needs_revision",
        },
    }


def _refined_requirement(title: str, description: str, refinement: dict[str, Any]) -> str:
    refined_scope = refinement.get("refined_scope") or refinement.get("first_pass_scope") or []
    surface = refinement.get("refined_surface") or refinement.get("surface")
    title_clean = title.strip().rstrip(".")
    if title_clean and refined_scope:
        return f"{title_clean}. Focus first on {', '.join(refined_scope[:2])}."
    if title_clean:
        return f"{title_clean}."
    description_clean = description.strip().splitlines()[0] if description.strip() else ""
    if description_clean and surface:
        return f"{description_clean.rstrip('.')}. Start with the {surface} path."
    return description_clean.rstrip(".") + "." if description_clean else ""


def _detect_flow(text: str) -> str | None:
    lowered = text.lower()
    mapping = {
        "login": ["login", "signin", "auth", "credential", "password", "otp"],
        "signup": ["signup", "register", "create account", "onboarding"],
        "payment": ["payment", "transaction", "billing", "invoice", "checkout"],
        "session": ["session", "token", "refresh", "expiry", "jwt"],
        "dashboard": ["dashboard", "home", "overview", "stats", "widget"],
        "profile": ["profile", "account", "settings", "user"],
    }
    best_flow = None
    best_score = 0
    for flow, keywords in mapping.items():
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_flow = flow
            best_score = score
    return best_flow


def _infer_actors(text: str) -> list[str]:
    lowered = text.lower()
    actors: list[str] = []
    if any(keyword in lowered for keyword in ["admin", "administrator"]):
        actors.append("admin")
    if any(keyword in lowered for keyword in ["user", "customer", "member", "login", "signup", "dashboard"]):
        actors.append("end_user")
    if "approver" in lowered or "approval" in lowered:
        actors.append("approver")
    return actors or ["end_user"]


def _business_rules(text: str, refinement: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    lowered = text.lower()
    validations = list(refinement.get("refined_validations", [])) or list(refinement.get("validations", []))
    if validations:
        rules.append(f"Preserve validation rules for {', '.join(_dedupe(validations)[:4])}.")
    if any(keyword in lowered for keyword in ["auth", "login", "password", "credential"]):
        rules.append("Preserve the existing authentication order and failure safety rules.")
    if any(keyword in lowered for keyword in ["session", "token", "otp"]):
        rules.append("Reuse the existing session or token lifecycle.")
    if any(keyword in lowered for keyword in ["payment", "transaction"]):
        rules.append("Do not mark payment success before verification completes.")
    return _dedupe(rules)


def _parse_acceptance_criteria(text: str, refinement: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*0123456789. ").strip()
        if line:
            items.append(line.rstrip(".") + ".")
    if not items:
        fields = list(refinement.get("refined_fields", [])) or list(refinement.get("fields", []))
        validations = list(refinement.get("refined_validations", [])) or list(refinement.get("validations", []))
        if fields:
            items.append(f"Support the required fields: {', '.join(_dedupe(fields)[:4])}.")
        if validations:
            items.append(f"Enforce the expected validations: {', '.join(_dedupe(validations)[:4])}.")
    return _dedupe(items)


def _detect_unknowns(text: str, variant: str | None) -> list[str]:
    lowered = text.lower()
    unknowns: list[str] = []
    if "otp" in lowered or variant == "phone_number":
        unknowns.append("Is OTP or a second-factor step required after the primary input succeeds?")
    if "dashboard" in lowered and "filter" in lowered:
        unknowns.append("Which filters are required in the first release?")
    if "approval" in lowered:
        unknowns.append("Who is allowed to approve or reject this flow?")
    return unknowns


def _text(work_item: dict, key: str) -> str:
    value = work_item.get(key)
    return str(value).strip() if value is not None else ""


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output
