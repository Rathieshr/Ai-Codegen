"""Normalization layer for semantic refinement output."""

from __future__ import annotations

import re
from typing import Any

from backend.refinement.canonical_vocabulary import (
    canonicalize_token,
    normalize_field,
    normalize_flow,
    normalize_surface,
    normalize_validation,
    normalize_variant,
)


MARKDOWN_PATTERN = re.compile(r"[`#*~]")
PATH_PATTERN = re.compile(r"(^|[\s])([A-Za-z]:\\|/|\.?/|[A-Za-z0-9_.-]+/).+\.[A-Za-z0-9]{1,8}\b")
CODE_PATTERN = re.compile(r"\b(class|def|function|return|import|from)\b")
SUSPICIOUS_COMMANDS = ("rm ", "git ", "curl ", "wget ", "npm ", "pip ", "python ", "bash ", "sh ")


def normalize_refinement(raw: dict) -> dict[str, Any]:
    """Map raw provider output into canonical normalized refinement metadata."""

    if not isinstance(raw, dict):
        raw = {}

    base_flows = _normalized_list(
        _collect(raw, "base_flows", "base_flow", "flows", "flow"),
        normalize_flow,
        limit=8,
    )
    variants = _normalized_list(
        _collect(raw, "variants", "variant"),
        normalize_variant,
        limit=6,
    )
    surfaces = _normalized_list(
        _collect(raw, "surfaces", "surface"),
        normalize_surface,
        limit=6,
    )
    fields = _normalized_list(
        _collect(raw, "fields", "field"),
        normalize_field,
        limit=10,
    )
    validations = _normalized_list(
        _collect(raw, "validations", "validation"),
        normalize_validation,
        limit=10,
    )
    scope_hints = _clean_text_list(_collect(raw, "scope_hints", "first_pass_scope", "refined_scope"), limit=8)
    actors = _clean_text_list(_collect(raw, "actors", "actor"), limit=6, canonicalize=True)
    states = _clean_text_list(_collect(raw, "states", "state"), limit=8, canonicalize=True)
    unknowns = _clean_text_list(_collect(raw, "unknowns", "open_questions"), limit=8)
    confidence = _confidence(raw.get("confidence"))

    _augment_from_combinations(base_flows, variants, surfaces, fields, validations)

    return {
        "base_flows": base_flows,
        "variants": variants,
        "surfaces": surfaces,
        "fields": fields,
        "validations": validations,
        "scope_hints": scope_hints,
        "actors": actors,
        "states": states,
        "unknowns": unknowns,
        "confidence": confidence,
        # Compatibility aliases for existing backend/extension flow.
        "base_flow": base_flows[0] if base_flows else None,
        "variant": variants[0] if variants else None,
        "surface": surfaces[0] if surfaces else None,
        "first_pass_scope": scope_hints,
    }


def _collect(raw: dict, *keys: str) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
    return values


def _normalized_list(values: list[Any], normalizer, limit: int) -> list[str]:
    output: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        normalized = normalizer(text)
        if normalized and normalized not in output:
            output.append(normalized)
        if len(output) >= limit:
            break
    return output


def _clean_text_list(values: list[Any], limit: int, canonicalize: bool = False) -> list[str]:
    output: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        normalized = canonicalize_token(text) if canonicalize else text
        if normalized and normalized not in output:
            output.append(normalized)
        if len(output) >= limit:
            break
    return output


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if MARKDOWN_PATTERN.search(text):
        text = MARKDOWN_PATTERN.sub("", text).strip()
    lowered = text.lower()
    if any(command in lowered for command in SUSPICIOUS_COMMANDS):
        return ""
    if PATH_PATTERN.search(text):
        return ""
    if CODE_PATTERN.search(lowered) and "/" in text:
        return ""
    return text[:160]


def _augment_from_combinations(
    base_flows: list[str],
    variants: list[str],
    surfaces: list[str],
    fields: list[str],
    validations: list[str],
) -> None:
    if "phone_number" in fields and "otp" in fields:
        _append_unique(base_flows, "login")
        _append_unique(base_flows, "otp_verification")
        _append_unique(variants, "phone_otp")
    elif "phone_number" in fields:
        _append_unique(base_flows, "login")
        _append_unique(variants, "phone_number")

    if "email" in fields and "password" in fields:
        _append_unique(base_flows, "login")
        _append_unique(variants, "email_password")

    if "attachment" in fields:
        _append_unique(base_flows, "document_upload")
        _append_unique(variants, "attachment_upload")

    if "filter_value" in fields:
        _append_unique(base_flows, "filter")
        _append_unique(variants, "list_filter")

    if "regex" in validations or "length_limit" in validations or "format" in validations:
        _append_unique(surfaces, "ui_validation")

    if not surfaces and any(flow in {"login", "signup", "otp_verification"} for flow in base_flows):
        _append_unique(surfaces, "authentication")


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _confidence(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"low", "medium", "high"} else "low"
