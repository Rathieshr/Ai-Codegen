"""Backend-only structured task refinement using an optional provider."""

from __future__ import annotations

import json
from typing import Any

from backend.refinement.canonical_vocabulary import (
    normalize_field,
    normalize_flow,
    normalize_surface,
    normalize_validation,
    normalize_variant,
)
from backend.refinement.provider import get_refinement_provider
from backend.refinement.schema_validator import validate_task_refinement


SYSTEM_PROMPT = (
    "You are ai-gen semantic refinement engine.\n\n"
    "Your job is to convert vague software work items into canonical engineering metadata.\n\n"
    "Map informal language into normalized concepts.\n\n"
    "Examples:\n"
    "- mobile number, phone no, contact number => phone_number\n"
    "- otp, sms code, one-time password, verification code => otp\n"
    "- sign in => login\n"
    "- register => signup\n\n"
    "You must return strict JSON only.\n\n"
    "Do not generate code.\n"
    "Do not invent file paths.\n"
    "Do not generate final prompts.\n"
    "Do not generate implementation steps.\n\n"
    "You only return normalized engineering metadata."
)

EXPECTED_SCHEMA = {
    "base_flows": ["string"],
    "variants": ["string"],
    "surfaces": ["string"],
    "fields": ["string"],
    "validations": ["string"],
    "scope_hints": ["string"],
    "actors": ["string"],
    "states": ["string"],
    "unknowns": ["string"],
    "confidence": "low|medium|high",
}


def refine_task(query: str, context: dict | None = None) -> dict[str, Any]:
    """Return structured refinement metadata or a safe disabled fallback."""

    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled():
        fallback = _deterministic_fallback(query, context)
        return {
            "semantic_mapping_applied": _has_semantic_metadata(fallback),
            "refinement_used": _has_semantic_metadata(fallback),
            "refinement_source": "deterministic_fallback" if _has_semantic_metadata(fallback) else "none",
            "refinement_provider": "deterministic_fallback",
            "refinement_reason": "provider unavailable",
            "phi_used": False,
            "phi_status": "not_configured",
            "refinement": fallback,
        }

    payload = {
        "query": query,
        "source": (context or {}).get("source"),
        "work_item": (context or {}).get("work_item"),
        "detected_intent": (context or {}).get("intent"),
        "detected_flow": (context or {}).get("detected_flow"),
        "constraints": (context or {}).get("constraints", []),
        "repo_hints": (context or {}).get("repo_hints", {}),
        "expected_json_schema": EXPECTED_SCHEMA,
    }
    raw = provider.refine_json(
        SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=True),
        max_tokens=800,
    )
    validated = validate_task_refinement(raw)
    if not any(validated.get(key) for key in ("base_flows", "variants", "surfaces", "fields", "validations", "scope_hints", "unknowns")):
        fallback = _deterministic_fallback(query, context)
        return {
            "semantic_mapping_applied": _has_semantic_metadata(fallback),
            "refinement_used": _has_semantic_metadata(fallback),
            "refinement_source": "deterministic_fallback" if _has_semantic_metadata(fallback) else "none",
            "refinement_provider": "deterministic_fallback",
            "refinement_reason": "provider returned no usable refinement",
            "phi_used": False,
            "phi_status": "unusable_response",
            "refinement": fallback,
        }

    return {
        "refinement_used": True,
        "semantic_mapping_applied": True,
        "refinement_source": "phi",
        "refinement_provider": "azure_phi",
        "refinement_reason": "provider returned structured refinement",
        "phi_used": True,
        "phi_status": "used",
        "refinement": validated,
    }


def _empty_refinement() -> dict[str, Any]:
    return validate_task_refinement({})


def _deterministic_fallback(query: str, context: dict | None = None) -> dict[str, Any]:
    text = " ".join(
        [
            query or "",
            str((context or {}).get("detected_flow") or ""),
            json.dumps((context or {}).get("work_item") or {}, ensure_ascii=True),
        ]
    ).lower()
    flows: list[str] = []
    variants: list[str] = []
    surfaces: list[str] = []
    fields: list[str] = []
    validations: list[str] = []
    scope_hints: list[str] = []
    actors: list[str] = []
    states: list[str] = []
    unknowns: list[str] = []

    for candidate in ["login", "signup", "forgot_password", "otp_verification", "dashboard", "payment", "approval", "document_upload", "settings", "search", "filter", "notification"]:
        normalized = normalize_flow(candidate)
        if normalized and (candidate.replace("_", " ") in text or candidate in text):
            _append(flows, normalized)

    if any(token in text for token in ["phone", "mobile", "contact number"]):
        _append(fields, normalize_field("phone_number"))
        _append(scope_hints, "phone number input")
    if any(token in text for token in ["otp", "sms code", "verification code", "one-time password"]):
        _append(fields, normalize_field("otp"))
        _append(flows, normalize_flow("otp_verification"))
        _append(scope_hints, "otp verification step")
        _append(unknowns, "Clarify OTP retry and expiry policy.")
    if "email" in text:
        _append(fields, normalize_field("email"))
    if "password" in text:
        _append(fields, normalize_field("password"))
    if any(token in text for token in ["attachment", "document upload", "file upload"]):
        _append(fields, normalize_field("attachment"))
        _append(flows, normalize_flow("document_upload"))
    if "role" in text:
        _append(fields, normalize_field("role"))
    if "amount" in text or "payment" in text:
        _append(fields, normalize_field("amount"))
        _append(flows, normalize_flow("payment"))
    if "search" in text:
        _append(fields, normalize_field("search_query"))
        _append(flows, normalize_flow("search"))
    if "filter" in text:
        _append(fields, normalize_field("filter_value"))
        _append(flows, normalize_flow("filter"))

    if "screen" in text or "page" in text or "dashboard" in text or "form" in text:
        _append(surfaces, normalize_surface("ui_screen"))
    if "validation" in text or "regex" in text or "limit" in text or "format" in text:
        _append(surfaces, normalize_surface("ui_validation"))
        _append(validations, normalize_validation("required"))
        _append(validations, normalize_validation("format"))
    if "api" in text or "endpoint" in text or "controller" in text:
        _append(surfaces, normalize_surface("api_controller"))
    if "service" in text or "logic" in text:
        _append(surfaces, normalize_surface("service_logic"))
    if any(token in text for token in ["auth", "login", "signup", "otp"]):
        _append(surfaces, normalize_surface("authentication"))
    if any(token in text for token in ["permission", "authorization", "role based"]):
        _append(surfaces, normalize_surface("authorization"))

    if "required" in text:
        _append(validations, normalize_validation("required"))
    if "regex" in text:
        _append(validations, normalize_validation("regex"))
    if "limit" in text or "length" in text:
        _append(validations, normalize_validation("length_limit"))
    if "unique" in text or "duplicate" in text:
        _append(validations, normalize_validation("uniqueness"))
    if "permission" in text or "role" in text:
        _append(validations, normalize_validation("permission_required"))
    if any(token in text for token in ["auth", "login", "signup"]):
        _append(validations, normalize_validation("auth_required"))

    if "user" in text or "customer" in text:
        _append(actors, "end_user")
    if "admin" in text:
        _append(actors, "admin")
    if "approver" in text or "approval" in text:
        _append(actors, "approver")

    if "loading" in text:
        _append(states, "loading")
    if "error" in text or "failure" in text:
        _append(states, "error")

    if "phone_number" in fields and "otp" in fields:
        _append(flows, normalize_flow("login"))
        _append(variants, normalize_variant("phone_otp"))
    elif "phone_number" in fields:
        _append(flows, normalize_flow("login"))
        _append(variants, normalize_variant("phone_number"))
    if "email" in fields and "password" in fields:
        _append(flows, normalize_flow("login"))
        _append(variants, normalize_variant("email_password"))
    if "filter_value" in fields:
        _append(variants, normalize_variant("list_filter"))
    if "attachment" in fields:
        _append(variants, normalize_variant("attachment_upload"))

    if not scope_hints and flows:
        scope_hints.extend([f"{flows[0]} primary flow", "smallest safe scope"])

    return validate_task_refinement(
        {
            "base_flows": flows,
            "variants": variants,
            "surfaces": surfaces,
            "fields": fields,
            "validations": validations,
            "scope_hints": scope_hints,
            "actors": actors,
            "states": states,
            "unknowns": unknowns,
            "confidence": "medium" if flows or fields else "low",
        }
    )


def _append(values: list[str], value: str | None) -> None:
    if value and value not in values:
        values.append(value)


def _has_semantic_metadata(refinement: dict[str, Any]) -> bool:
    return any(
        refinement.get(key)
        for key in ("base_flows", "variants", "surfaces", "fields", "validations", "scope_hints", "actors", "states", "unknowns")
    )
