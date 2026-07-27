"""Normalize and validate evidence-grounded reasoning responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.ai.provider import ProviderParseError, ProviderResponseParser


@dataclass
class ResponseValidation:
    valid: bool
    value: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ResponseValidator:
    REQUIRED = ("recommendation", "reasoning", "alternatives", "evidence", "confidence")

    def __init__(self, parser: ProviderResponseParser | None = None) -> None:
        self.parser = parser or ProviderResponseParser()

    def validate(
        self,
        response: Any,
        evidence_catalog: list[dict[str, Any]],
    ) -> ResponseValidation:
        metadata = _metadata(response)
        candidate = _content(response)
        try:
            value = candidate if isinstance(candidate, dict) else self.parser.parse_json(candidate).parsed_json
        except (ProviderParseError, ValueError, TypeError) as error:
            return ResponseValidation(False, errors=[f"parse_error: {error}"], metadata=metadata)

        errors: list[str] = []
        for field_name in self.REQUIRED:
            if field_name not in value:
                errors.append(f"missing_field: {field_name}")
        if not _non_empty(value.get("recommendation")):
            errors.append("empty_field: recommendation")
        for field_name in ("reasoning", "alternatives", "evidence"):
            if field_name in value and not isinstance(value.get(field_name), list):
                errors.append(f"invalid_type: {field_name}")

        allowed = {
            str(item.get("referenceId"))
            for item in evidence_catalog
            if item.get("referenceId")
        }
        accepted_evidence: list[dict[str, Any]] = []
        warnings: list[str] = []
        for item in value.get("evidence") or []:
            normalized = item if isinstance(item, dict) else {"referenceId": str(item)}
            reference = str(normalized.get("referenceId") or "")
            if reference in allowed:
                accepted_evidence.append(normalized)
            else:
                warnings.append(f"Unknown evidence reference removed: {reference or 'empty'}")
        value["evidence"] = accepted_evidence
        if allowed and not accepted_evidence:
            errors.append("missing_valid_evidence")

        value.setdefault("risks", [])
        value.setdefault("tradeOffs", [])
        value.setdefault("impact", {})
        return ResponseValidation(not errors, value, errors, warnings, metadata)


def _content(response: Any) -> Any:
    if isinstance(response, dict) and "_reasoning_metadata" in response and "content" in response:
        return response["content"]
    return response


def _metadata(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("_reasoning_metadata"), dict):
        return dict(response["_reasoning_metadata"])
    return {}


def _non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return bool(value)
    return value is not None
