"""Business-analysis stage for the structured assistant pipeline."""

from __future__ import annotations

import json
from typing import Any

from backend.refinement.provider import get_refinement_provider
from backend.prompt_budget import default_json_sections, refine_json_with_budget


QUESTION_VALIDATION_SYSTEM_PROMPT = (
    "You are ai-gen's clarification validation engine.\n"
    "Decide whether reviewer feedback clearly answers a specific open requirement question.\n"
    "Return strict JSON only.\n"
    "Schema: {\"answered\": true|false, \"confidence\": \"low|medium|high\"}\n"
    "Do not generate implementation steps, code, or file paths."
)


def run_ba_assistant(
    work_item: dict,
    refinement: dict | None = None,
    review_context: dict | None = None,
    effective_context: dict | None = None,
) -> dict:
    """Build a deterministic BA artifact from work item text and optional refinement."""

    refinement = refinement or {}
    review_context = review_context or {}
    title = _text(work_item, "title")
    description = _text(work_item, "description")
    acceptance_text = _text(work_item, "acceptanceCriteria") or _text(work_item, "acceptance_criteria")
    effective_text = str((effective_context or {}).get("effective_text") or work_item.get("effective_context_text") or "").strip()
    tags = [str(tag).strip() for tag in work_item.get("tags", []) if str(tag).strip()]
    combined = " ".join(part for part in [title, description, acceptance_text, effective_text, " ".join(tags)] if part).strip()
    variants = list(refinement.get("refined_variants", [])) or list(refinement.get("variants", []))
    variant = _first(variants) or refinement.get("refined_variant") or refinement.get("variant")
    refined_flows = list(refinement.get("refined_base_flows", [])) or list(refinement.get("base_flows", []))
    base_flow = _first(refined_flows) or refinement.get("refined_base_flow") or refinement.get("base_flow") or _detect_flow(combined)
    actors = _infer_actors(combined)
    flows = _dedupe(refined_flows + ([base_flow] if base_flow else []))
    business_rules = _business_rules(combined, refinement)
    acceptance_criteria = _parse_acceptance_criteria(acceptance_text, refinement, review_context, effective_context)
    unknowns = _dedupe(
        list(refinement.get("refinement_unknowns", []))
        + list(refinement.get("unknowns", []))
        + _detect_unknowns(combined, variant)
        + _reviewer_unknowns(review_context)
    )
    unknowns = _filter_answered_unknowns(unknowns, review_context, effective_context)
    refined_requirement = _refined_requirement(title, description, refinement)
    feedback_summary = _feedback_summary(review_context, effective_context)
    if feedback_summary:
        refined_requirement = f"{refined_requirement.rstrip('.')} Review clarifications: {feedback_summary}."

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
        "variants": _dedupe(variants + ([variant] if variant else [])),
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


def _feedback_summary(review_context: dict[str, Any], effective_context: dict[str, Any] | None = None) -> str:
    comments = [str(item.get("comment", "")).strip() for item in review_context.get("review_feedback", [])]
    comments.extend(
        str(item.get("body", "")).strip()
        for item in (effective_context or {}).get("clarifications", [])
        if str(item.get("body", "")).strip()
    )
    return "; ".join(comment for comment in comments[:2] if comment)


def _reviewer_unknowns(review_context: dict[str, Any]) -> list[str]:
    return [str(item.get("message", "")).strip() for item in review_context.get("critic_findings", []) if item.get("severity") == "blocking"]


def _filter_answered_unknowns(
    unknowns: list[str],
    review_context: dict[str, Any],
    effective_context: dict[str, Any] | None = None,
) -> list[str]:
    feedback_comments = [
        str(item.get("comment", "")).strip()
        for item in review_context.get("review_feedback", [])
        if str(item.get("comment", "")).strip()
    ]
    feedback_comments.extend(
        str(item.get("body", "")).strip()
        for item in (effective_context or {}).get("clarifications", [])
        if str(item.get("body", "")).strip()
    )
    feedback_text = " ".join(comment.lower() for comment in feedback_comments)
    if not feedback_text:
        return unknowns

    provider = get_refinement_provider()
    filtered: list[str] = []
    for unknown in unknowns:
        if _is_answered_unknown(str(unknown), feedback_text):
            continue
        if _provider_answers_unknown(str(unknown), feedback_comments, provider):
            continue
        filtered.append(unknown)
    return filtered


def _is_answered_unknown(unknown: str, feedback_text: str) -> bool:
    question = unknown.strip().lower()
    if not question:
        return False

    has_second_factor_answer = (
        "second factor" in feedback_text
        or "second-factor" in feedback_text
        or "otp" in feedback_text
        or "verification code" in feedback_text
    ) and any(
        phrase in feedback_text
        for phrase in [
            "needed",
            "required",
            "yes",
        ]
    )

    if ("otp" in question or "second-factor" in question or "second factor" in question) and (
        has_second_factor_answer
        or any(
            phrase in feedback_text
            for phrase in [
                "otp is needed",
                "otp is required",
                "otp needed",
                "otp required",
                "verification code is needed",
                "verification code is required",
            ]
        )
    ):
        return True

    if "retry" in question and any(
        phrase in feedback_text
        for phrase in [
            "retry policy",
            "retry allowed",
            "retry limit",
            "3 times",
            "3 attempts",
            "three times",
            "three attempts",
            "max 3",
            "maximum 3",
        ]
    ):
        return True

    if "expiry" in question and "expiry" in feedback_text:
        return True

    if "filters" in question and any(phrase in feedback_text for phrase in ["filter", "filters"]):
        return True

    if "who is allowed to approve" in question and any(
        phrase in feedback_text for phrase in ["admin", "manager", "approver", "reviewer", "allowed to approve"]
    ):
        return True

    return False


def _provider_answers_unknown(unknown: str, feedback_comments: list[str], provider: Any) -> bool:
    if provider is None or not getattr(provider, "is_enabled", lambda: False)():
        return False

    payload = {
        "open_question": unknown,
        "reviewer_feedback": feedback_comments[:6],
        "expected_json_schema": {
            "answered": "true|false",
            "confidence": "low|medium|high",
        },
    }
    try:
        raw = refine_json_with_budget(
            provider,
            default_json_sections(
                role="Business analyst clarification validator",
                objective="Decide whether reviewer feedback answers the open question.",
                current_work_item=payload,
                instructions="Return JSON only with answered and confidence.",
                output_schema=payload["expected_json_schema"],
            ),
            operation="ba_question_validation",
            system_prompt=QUESTION_VALIDATION_SYSTEM_PROMPT,
            max_tokens=120,
        )
    except Exception:
        return False
    if not isinstance(raw, dict):
        return False
    answered = raw.get("answered")
    if isinstance(answered, bool):
        return answered
    if isinstance(answered, str):
        return answered.strip().lower() == "true"
    return False


def _refined_requirement(title: str, description: str, refinement: dict[str, Any]) -> str:
    refined_scope = refinement.get("refined_scope") or refinement.get("scope_hints") or refinement.get("first_pass_scope") or []
    surfaces = list(refinement.get("refined_surfaces", [])) or list(refinement.get("surfaces", []))
    surface = _first(surfaces) or refinement.get("refined_surface") or refinement.get("surface")
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


def _parse_acceptance_criteria(
    text: str,
    refinement: dict[str, Any],
    review_context: dict[str, Any],
    effective_context: dict[str, Any] | None = None,
) -> list[str]:
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
        variants = list(refinement.get("refined_variants", [])) or list(refinement.get("variants", []))
        if "phone_otp" in variants:
            items.append("Authenticate the user with phone number entry followed by OTP verification.")
    missing_acceptance_criteria = any(
        "acceptance criteria" in str(item.get("message", "")).lower()
        for item in review_context.get("critic_findings", [])
    )
    feedback_comments = [
        str(feedback.get("comment", "")).strip()
        for feedback in review_context.get("review_feedback", [])
        if str(feedback.get("comment", "")).strip()
    ]
    feedback_comments.extend(
        str(item.get("body", "")).strip()
        for item in (effective_context or {}).get("clarifications", [])
        if str(item.get("body", "")).strip()
    )
    for comment in feedback_comments:
        if not comment:
            continue
        if "acceptance criteria" in comment.lower() or "acceptance:" in comment.lower():
            items.extend(_extract_acceptance_items(comment))
            continue
        if missing_acceptance_criteria and not items:
            items.extend(_extract_acceptance_items(comment))
    return _dedupe(items)


def _extract_acceptance_items(comment: str) -> list[str]:
    normalized = comment.strip()
    lowered = normalized.lower()
    for prefix in ("acceptance criteria:", "acceptance:"):
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    parts = [segment.strip() for segment in normalized.replace("\r", "\n").splitlines()]
    if len(parts) == 1:
        parts = [segment.strip() for segment in normalized.split(";")]
    output: list[str] = []
    for part in parts:
        line = part.strip().lstrip("-*0123456789. ").strip()
        if line:
            normalized = line[0].upper() + line[1:] if line else line
            output.append(normalized.rstrip(".") + ".")
    return output


def _detect_unknowns(text: str, variant: str | None) -> list[str]:
    lowered = text.lower()
    unknowns: list[str] = []
    if "otp" in lowered or variant in {"phone_number", "phone_otp", "otp_only"}:
        unknowns.append("Is OTP or a second-factor step required after the primary input succeeds?")
        if "retry" not in lowered and "attempt" not in lowered and "expire" not in lowered and "expiry" not in lowered:
            unknowns.append("Clarify OTP retry and expiry policy.")
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


def _first(values: list[str]) -> str | None:
    for value in values:
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None
