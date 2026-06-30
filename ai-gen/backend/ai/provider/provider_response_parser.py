"""Parse normalized provider response content as a JSON object."""

from __future__ import annotations

import json
import re
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
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as error:
                last_error = error
                continue
            if not isinstance(parsed, dict):
                raise ProviderParseError(
                    "NonDictParsedJson",
                    "Provider returned JSON, but it was not an object.",
                    raw_preview=content[:1500],
                    source_format=source_format,
                )
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
