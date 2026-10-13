"""Parse normalized provider response content as a JSON object."""

from __future__ import annotations

import json
import re
import ast
from typing import Any

from .provider_parse_error import ProviderParseError
from .provider_response_normalizer import ProviderResponseNormalizer
from .provider_response_types import ParsedProviderResponse

_FENCED_BLOCK_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


class ProviderResponseParser:
    """Normalize provider envelopes and parse JSON object payloads."""

    def __init__(self, normalizer: ProviderResponseNormalizer | None = None) -> None:
        self.normalizer = normalizer or ProviderResponseNormalizer()

    def parse_json(self, response: Any) -> ParsedProviderResponse:
        normalized = self.normalizer.normalize(response)
        parsed = self._parse_content(normalized.content, normalized.source_format)
        return ParsedProviderResponse(normalized=normalized, parsed_json=parsed)

    def _parse_content(self, content: str, source_format: str) -> dict[str, Any]:
        text = _strip_markdown_json(content)
        candidates = [text]
        balanced = _first_balanced_json_object(text)
        if balanced and balanced != text:
            candidates.append(balanced)

        last_error: Exception | None = None
        for candidate in candidates:
            if not candidate.strip():
                continue
            parsed, error = _parse_json_object_candidate(candidate)
            if error:
                last_error = error
                continue
            return parsed

        if "{" not in text:
            raise ProviderParseError(
                "NoJsonObjectFound",
                "Provider response did not contain a JSON object.",
                raw_preview=content[:1500],
                source_format=source_format,
            )

        raise ProviderParseError(
            type(last_error).__name__ if last_error else "JSONDecodeError",
            "Provider response contained JSON-like content but it could not be parsed.",
            raw_preview=content[:1500],
            source_format=source_format,
        )


def parse_provider_response_json(response: Any) -> ParsedProviderResponse:
    return ProviderResponseParser().parse_json(response)


def _strip_markdown_json(content: Any) -> str:
    if not isinstance(content, str):
        return json.dumps(content, ensure_ascii=False)
    text = content.strip()
    fenced = _FENCED_BLOCK_RE.search(text)
    if fenced:
        return fenced.group(1).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _first_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


def _parse_json_object_candidate(candidate: str) -> tuple[dict[str, Any], Exception | None]:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as first_error:
        repaired = _repair_json_like(candidate)
        if repaired != candidate:
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError:
                parsed, literal_error = _parse_python_literal(candidate)
                if literal_error:
                    return {}, first_error
        else:
            parsed, literal_error = _parse_python_literal(candidate)
            if literal_error:
                return {}, first_error
    if not isinstance(parsed, dict):
        raise ProviderParseError(
            "NonDictParsedJson",
            "Provider returned JSON, but it was not an object.",
            raw_preview=candidate[:1500],
            source_format="normalized_content",
        )
    return parsed, None


def _parse_python_literal(candidate: str) -> tuple[Any, Exception | None]:
    try:
        return ast.literal_eval(candidate), None
    except (SyntaxError, ValueError) as error:
        return {}, error


def _repair_json_like(candidate: str) -> str:
    repaired = candidate.strip()
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    return repaired
