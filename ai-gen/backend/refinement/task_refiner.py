"""Backend-only structured task refinement using an optional provider."""

from __future__ import annotations

import json
import os
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

EPIC_STAGE_SCHEMAS = {
    "epic_analysis": {
        "goal": "string",
        "scope": ["string"],
        "business_outcomes": ["string"],
        "assumptions": ["string"],
        "risks": ["string"],
        "dependency_notes": ["string"],
    },
    "feature_generation": {
        "domain": "string",
        "features": ["string"],
    },
    "story_generation": {
        "stories": ["string"],
    },
    "review": {
        "gaps": ["string"],
        "unknowns": ["string"],
        "risks": ["string"],
    },
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
            "provider_used": "deterministic_fallback",
            "refinement_reason": "provider unavailable",
            "phi_used": False,
            "phi_status": "not_configured",
            "phi_raw_response_preview": "",
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
    probe = getattr(provider, "probe_json", None)
    probe_result: dict[str, Any] | None = None
    if callable(probe):
        candidate = probe(
            SYSTEM_PROMPT,
            json.dumps(payload, ensure_ascii=True),
            max_tokens=_refiner_max_tokens(),
            response_format_enabled=False,
            allow_retry_without_response_format=False,
        )
        if isinstance(candidate, dict):
            probe_result = candidate
            raw = probe_result.get("parsed_json") if isinstance(probe_result.get("parsed_json"), dict) else {}
        else:
            raw = provider.refine_json(
                SYSTEM_PROMPT,
                json.dumps(payload, ensure_ascii=True),
                max_tokens=_refiner_max_tokens(),
            )
    else:
        raw = provider.refine_json(
            SYSTEM_PROMPT,
            json.dumps(payload, ensure_ascii=True),
            max_tokens=_refiner_max_tokens(),
        )
    raw_preview = _preview_probe_result(probe_result, raw)
    validated = validate_task_refinement(raw)
    if not any(validated.get(key) for key in ("base_flows", "variants", "surfaces", "fields", "validations", "scope_hints", "unknowns")):
        fallback = _deterministic_fallback(query, context)
        return {
            "semantic_mapping_applied": _has_semantic_metadata(fallback),
            "refinement_used": _has_semantic_metadata(fallback),
            "refinement_source": "deterministic_fallback" if _has_semantic_metadata(fallback) else "none",
            "refinement_provider": "deterministic_fallback",
            "provider_used": "deterministic_fallback",
            "refinement_reason": "provider returned no usable refinement",
            "phi_used": False,
            "phi_status": "unusable_response",
            "phi_raw_response_preview": raw_preview,
            "refinement": fallback,
        }

    return {
        "refinement_used": True,
        "semantic_mapping_applied": True,
        "refinement_source": "phi",
        "refinement_provider": "azure_phi",
        "provider_used": "azure_phi",
        "refinement_reason": "provider returned structured refinement",
        "phi_used": True,
        "phi_status": "used",
        "phi_raw_response_preview": raw_preview,
        "refinement": validated,
    }


def refine_epic_stage(
    stage: str,
    work_item: dict[str, Any],
    upstream: dict[str, Any] | None = None,
    effective_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = get_refinement_provider()
    if provider is not None and provider.is_enabled():
        probed = _probe_epic_stage(provider, stage, work_item, upstream, effective_context)
        parsed = probed.get("parsed_json") if isinstance(probed.get("parsed_json"), dict) else {}
        parsed = _coerce_epic_stage_payload(stage, parsed, work_item, upstream, effective_context)
        if _epic_stage_payload_is_usable(stage, parsed):
            return {
                "provider_used": "azure_phi",
                "phi_used": True,
                "phi_status": "used",
                "phi_raw_response_preview": _preview_probe_result(probed, parsed),
                "parsed": parsed,
            }
        domain_fallback = _domain_fallback_epic_stage(stage, work_item, upstream, effective_context)
        if _epic_stage_payload_is_usable(stage, domain_fallback):
            return {
                "provider_used": "domain_fallback",
                "phi_used": bool(probed.get("http_status")),
                "phi_status": "unusable_response" if probed.get("http_status") else "unavailable",
                "phi_raw_response_preview": _preview_probe_result(probed, parsed),
                "parsed": domain_fallback,
            }
    deterministic = _deterministic_epic_stage(stage, work_item, upstream, effective_context)
    return {
        "provider_used": "deterministic_fallback",
        "phi_used": False,
        "phi_status": "not_configured" if provider is None or not provider.is_enabled() else "unusable_response",
        "phi_raw_response_preview": "",
        "parsed": deterministic,
    }


def _preview_probe_result(probe_result: dict[str, Any] | None, raw: dict[str, Any]) -> str:
    if not isinstance(probe_result, dict):
        return ""
    for key in ("raw_content", "raw_response_preview"):
        value = probe_result.get(key)
        if isinstance(value, str) and value.strip():
            return value[:1500]
    parsed = probe_result.get("parsed_json")
    if parsed:
        try:
            return json.dumps(parsed, ensure_ascii=True)[:1500]
        except (TypeError, ValueError):
            return str(parsed)[:1500]
    attempts = probe_result.get("attempts")
    if isinstance(attempts, list):
        for attempt in reversed(attempts):
            if not isinstance(attempt, dict):
                continue
            for key in ("raw_content", "raw_response_preview"):
                value = attempt.get(key)
                if isinstance(value, str) and value.strip():
                    return value[:1500]
            attempt_parsed = attempt.get("parsed_json")
            if attempt_parsed:
                try:
                    return json.dumps(attempt_parsed, ensure_ascii=True)[:1500]
                except (TypeError, ValueError):
                    return str(attempt_parsed)[:1500]
            for key in ("failure_message", "error_message", "parse_error"):
                value = attempt.get(key)
                if isinstance(value, str) and value.strip():
                    return value[:1500]
    if raw:
        try:
            return json.dumps(raw, ensure_ascii=True)[:1500]
        except (TypeError, ValueError):
            return str(raw)[:1500]
    for key in ("failure_message", "error_message", "parse_error"):
        value = probe_result.get(key)
        if isinstance(value, str) and value.strip():
            return value[:1500]
    return ""


def _refiner_max_tokens() -> int:
    try:
        return max(80, int(os.getenv("AI_GEN_REFINER_MAX_TOKENS", "300")))
    except (TypeError, ValueError):
        return 300


def _probe_epic_stage(provider: Any, stage: str, work_item: dict[str, Any], upstream: dict[str, Any] | None, effective_context: dict[str, Any] | None) -> dict[str, Any]:
    prompt = {
        "stage": stage,
        "work_item": {
            "id": work_item.get("id"),
            "type": work_item.get("type"),
            "title": work_item.get("title"),
            "description": work_item.get("description"),
            "acceptance_criteria": work_item.get("acceptanceCriteria") or work_item.get("acceptance_criteria"),
            "tags": work_item.get("tags", []),
        },
        "upstream": upstream or {},
        "effective_text": (effective_context or {}).get("effective_text", "")[:4000],
        "expected_json_schema": EPIC_STAGE_SCHEMAS.get(stage, {}),
    }
    system_prompt = (
        "You are ai-gen epic planning refiner. Return strict JSON only. "
        f"Generate only the JSON schema for stage {stage}."
    )
    return provider.probe_json(
        system_prompt,
        json.dumps(prompt, ensure_ascii=True),
        max_tokens=220 if stage == "epic_analysis" else 260,
        response_format_enabled=False,
        allow_retry_without_response_format=False,
    )


def _epic_stage_payload_is_usable(stage: str, payload: dict[str, Any]) -> bool:
    if stage == "epic_analysis":
        return bool(payload.get("goal") or payload.get("business_outcomes"))
    if stage == "feature_generation":
        return bool(payload.get("features"))
    if stage == "story_generation":
        return bool(payload.get("stories"))
    if stage == "review":
        return any(payload.get(key) for key in ("gaps", "unknowns", "risks"))
    return False


def _coerce_epic_stage_payload(
    stage: str,
    payload: dict[str, Any],
    work_item: dict[str, Any],
    upstream: dict[str, Any] | None,
    effective_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if stage == "epic_analysis":
        goal = str(payload.get("goal") or work_item.get("title") or "Epic goal").strip()
        scope = list(payload.get("scope") or [])
        if not scope:
            scope = [item for item in [goal, str(work_item.get("description") or "").strip()] if item][:3]
        return {
            "goal": goal,
            "scope": scope,
            "business_outcomes": _string_list(payload.get("business_outcomes")),
            "assumptions": _string_list(payload.get("assumptions")),
            "risks": _string_list(payload.get("risks")),
            "dependency_notes": _string_list(payload.get("dependency_notes") or payload.get("dependencies")),
        }
    if stage == "feature_generation":
        features = _extract_feature_titles(payload)
        return {
            "domain": str(payload.get("domain") or _infer_domain(" ".join([
                str(work_item.get("title") or ""),
                str(work_item.get("description") or ""),
                str((effective_context or {}).get("effective_text") or ""),
            ]).lower())).strip(),
            "features": features,
        }
    if stage == "story_generation":
        stories = _extract_story_titles(payload)
        if not stories:
            stories = _story_title_hints(
                str(work_item.get("title") or "Epic"),
                list((upstream or {}).get("features") or (upstream or {}).get("generated_features") or []),
            )
        return {"stories": stories}
    if stage == "review":
        return {
            "gaps": _string_list(payload.get("gaps") or payload.get("missing_acceptance_criteria")),
            "unknowns": _string_list(payload.get("unknowns") or payload.get("dependency_issues") or payload.get("ownership_gaps")),
            "risks": _string_list(payload.get("risks")),
        }
    return payload


def _domain_fallback_epic_stage(stage: str, work_item: dict[str, Any], upstream: dict[str, Any] | None, effective_context: dict[str, Any] | None) -> dict[str, Any]:
    title = str(work_item.get("title") or "").strip()
    description = str(work_item.get("description") or "").strip()
    text = " ".join([title, description, str((effective_context or {}).get("effective_text") or "")]).lower()
    domain = _infer_domain(text)
    if stage == "epic_analysis":
        return {
            "goal": title or "Epic goal",
            "scope": [item for item in [title, description] if item][:3],
            "business_outcomes": _business_outcome_hints(domain, title),
            "assumptions": _assumption_hints(domain),
            "risks": _risk_hints(domain),
            "dependency_notes": _dependency_hints(domain),
        }
    if stage == "feature_generation":
        return {
            "domain": domain,
            "features": _feature_title_hints(domain, title),
        }
    if stage == "story_generation":
        features = list((upstream or {}).get("features") or (upstream or {}).get("generated_features") or [])
        return {
            "stories": _story_title_hints(title, features),
        }
    if stage == "review":
        return {
            "gaps": [],
            "unknowns": [],
            "risks": _risk_hints(domain)[:2],
        }
    return {}


def _deterministic_epic_stage(stage: str, work_item: dict[str, Any], upstream: dict[str, Any] | None, effective_context: dict[str, Any] | None) -> dict[str, Any]:
    return _domain_fallback_epic_stage(stage, work_item, upstream, effective_context)


def _infer_domain(text: str) -> str:
    if any(token in text for token in ["e-commerce", "ecommerce", "commerce", "shopping", "cart", "checkout", "retail", "mobile app", "ios", "android"]):
        return "mobile_commerce"
    if any(token in text for token in ["hotel", "booking", "reservation", "guest"]):
        return "hospitality"
    if any(token in text for token in ["auth", "identity", "login", "otp"]):
        return "authentication"
    if any(token in text for token in ["meter", "analytics", "energy"]):
        return "analytics"
    if any(token in text for token in ["community", "member", "society"]):
        return "community_management"
    if any(token in text for token in ["property", "airbnb", "host"]):
        return "property_management"
    return "platform"


def _feature_title_hints(domain: str, title: str) -> list[str]:
    seeds = {
        "hospitality": ["Search and Availability", "Booking Conversation Flow", "Payment and Confirmation", "Guest Notifications"],
        "authentication": ["Phone Number Sign-In", "OTP Verification", "Session and Device Trust", "Recovery and Account Security"],
        "analytics": ["Usage Dashboard", "Anomaly Detection", "Alerting and Notifications", "Reporting and Exports"],
        "community_management": ["Member Onboarding", "Announcements and Notices", "Maintenance Requests", "Billing and Dues"],
        "property_management": ["Listing Management", "Reservation Operations", "Guest Messaging", "Payouts and Accounting"],
        "mobile_commerce": ["Mobile Shopping Experience", "Cart and Checkout Flow", "Order Visibility", "Commerce Operations"],
        "platform": ["User Experience Foundation", "Core Workflow Automation", "Reporting and Visibility", "Operational Controls"],
    }
    base = seeds.get(domain, seeds["platform"])
    prefix = title.strip() or "Epic"
    return [f"{prefix}: {item}" for item in base[:4]]


def _story_title_hints(title: str, features: list[Any]) -> list[str]:
    story_titles: list[str] = []
    normalized_features = []
    for feature in features[:4]:
        if isinstance(feature, dict):
            normalized_features.append(str(feature.get("title") or feature.get("name") or "").strip())
        else:
            normalized_features.append(str(feature).strip())
    normalized_features = [item for item in normalized_features if item]
    for feature in normalized_features[:4]:
        story_titles.extend(_story_titles_for_feature(feature))
    if story_titles:
        return story_titles
    base = title.strip() or "Epic"
    return [f"{base}: Define primary user journey", f"{base}: Validate successful completion"]


def _story_titles_for_feature(feature: str) -> list[str]:
    cleaned = feature.strip()
    lower = cleaned.lower()
    if any(token in lower for token in ["cart", "checkout", "payment", "workflow", "automation"]):
        return [
            f"{cleaned}: Complete checkout with delivery and payment details",
            f"{cleaned}: Confirm order after successful payment",
        ]
    if any(token in lower for token in ["order", "visibility", "report", "status", "notification"]):
        return [
            f"{cleaned}: View order history and order status",
            f"{cleaned}: Receive order confirmation and delivery updates",
        ]
    if any(token in lower for token in ["operation", "control", "inventory", "admin"]):
        return [
            f"{cleaned}: Manage product availability and inventory status",
            f"{cleaned}: Configure operational rules for mobile commerce",
        ]
    if any(token in lower for token in ["shopping", "experience", "catalog", "user experience", "mobile"]):
        return [
            f"{cleaned}: Browse products and product details",
            f"{cleaned}: Manage cart from mobile screens",
        ]
    return [
        f"{cleaned}: Define primary user journey",
        f"{cleaned}: Validate successful completion",
    ]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _extract_feature_titles(payload: dict[str, Any]) -> list[str]:
    features: list[str] = []
    for item in payload.get("features") or []:
        title = _draft_title(item)
        if title:
            features.append(title)
    for item in payload.get("generated_features") or payload.get("proposed_features") or payload.get("generated_work_items") or payload.get("proposed_work_items") or []:
        if _draft_type(item) == "feature":
            title = _draft_title(item)
            if title:
                features.append(title)
    return _dedupe_strings(features)


def _extract_story_titles(payload: dict[str, Any]) -> list[str]:
    stories: list[str] = []
    for item in payload.get("stories") or []:
        title = _draft_title(item)
        if title:
            stories.append(title)
    work_items = payload.get("generated_work_items") or payload.get("proposed_work_items") or []
    for item in work_items:
        stories.extend(_collect_story_titles(item))
    return _dedupe_strings(stories)


def _collect_story_titles(item: Any) -> list[str]:
    if not isinstance(item, dict):
        title = str(item).strip()
        return [title] if title else []
    found: list[str] = []
    if _draft_type(item) == "user story":
        title = _draft_title(item)
        if title:
            found.append(title)
    for child in item.get("child_drafts") or item.get("children") or []:
        found.extend(_collect_story_titles(child))
    return found


def _draft_title(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("title") or item.get("name") or "").strip()
    return str(item).strip()


def _draft_type(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("draft_type") or item.get("type") or "").strip().lower()


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output


def _business_outcome_hints(domain: str, title: str) -> list[str]:
    mapping = {
        "hospitality": ["Reduce booking friction in conversational channels.", "Improve conversion from inquiry to confirmed reservation."],
        "authentication": ["Reduce login friction without weakening security.", "Improve verification completion rate."],
        "analytics": ["Improve visibility into usage patterns.", "Reduce time to investigate anomalies."],
        "community_management": ["Reduce operational coordination overhead.", "Improve resident communication quality."],
        "property_management": ["Reduce host operational workload.", "Improve booking and guest coordination quality."],
        "mobile_commerce": ["Improve mobile shopping conversion.", "Reduce friction from product discovery through checkout."],
        "platform": ["Improve delivery speed for the core platform.", "Reduce operational friction in the primary workflow."],
    }
    return mapping.get(domain, mapping["platform"])


def _assumption_hints(domain: str) -> list[str]:
    return [
        f"Assume the {domain.replace('_', ' ')} workflow will integrate with existing backend services.",
        "Assume the first release should prioritize the primary happy path before edge-case expansion.",
    ]


def _risk_hints(domain: str) -> list[str]:
    return [
        f"Cross-team dependencies may slow {domain.replace('_', ' ')} delivery.",
        "Scope growth across related stories may reduce planning clarity.",
        "Integration assumptions may need confirmation before implementation begins.",
    ]


def _dependency_hints(domain: str) -> list[str]:
    return [
        f"{domain.replace('_', ' ').title()} workflow dependencies should be confirmed with backend and UX owners.",
        "External integrations and notification paths should be validated before downstream task creation.",
    ]


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
