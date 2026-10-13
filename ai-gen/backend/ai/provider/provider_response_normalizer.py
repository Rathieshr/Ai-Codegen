"""Normalize different AI provider response envelopes into text content."""

from __future__ import annotations

import json
from typing import Any

from .provider_response_types import NormalizedProviderResponse


class ProviderResponseNormalizer:
    """Extract model content from common provider response shapes."""

    def normalize(self, response: Any) -> NormalizedProviderResponse:
        if isinstance(response, bytes):
            response = response.decode("utf-8", errors="replace")

        if isinstance(response, str):
            return self._normalize_string(response)

        if isinstance(response, dict):
            return self._normalize_mapping(response, raw_response=response)

        return NormalizedProviderResponse(
            raw_response=response,
            content=json.dumps(response, ensure_ascii=False),
            source_format=type(response).__name__,
        )

    def _normalize_string(self, response: str) -> NormalizedProviderResponse:
        text = response.strip()
        if not text:
            return NormalizedProviderResponse(raw_response=response, content="", source_format="plain_text")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return NormalizedProviderResponse(raw_response=response, content=text, source_format="plain_text")

        if isinstance(parsed, dict):
            normalized = self._normalize_mapping(parsed, raw_response=response)
            if normalized.source_format != "json_object":
                return normalized
            return NormalizedProviderResponse(raw_response=response, content=text, source_format="json_string")

        if isinstance(parsed, str):
            return NormalizedProviderResponse(raw_response=response, content=parsed, source_format="json_string_value")

        return NormalizedProviderResponse(raw_response=response, content=text, source_format="json_string")

    def _normalize_mapping(self, response: dict[str, Any], *, raw_response: Any) -> NormalizedProviderResponse:
        content = self._chat_completion_content(response)
        if content is not None:
            return NormalizedProviderResponse(
                raw_response=raw_response,
                content=content,
                source_format="chat_completions",
                metadata={"provider_shape": "choices[0].message.content"},
            )

        for key, source_format in (
            ("response", "ollama_response"),
            ("content", "content_field"),
            ("output_text", "output_text"),
            ("text", "text_field"),
        ):
            value = response.get(key)
            if isinstance(value, str):
                return NormalizedProviderResponse(
                    raw_response=raw_response,
                    content=value,
                    source_format=source_format,
                    metadata={"provider_shape": key},
                )

        message = response.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return NormalizedProviderResponse(
                raw_response=raw_response,
                content=message["content"],
                source_format="message_content",
                metadata={"provider_shape": "message.content"},
            )

        return NormalizedProviderResponse(
            raw_response=raw_response,
            content=json.dumps(response, ensure_ascii=False),
            source_format="json_object",
        )

    def _chat_completion_content(self, response: dict[str, Any]) -> str | None:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        message = first.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        delta = first.get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("content"), str):
            return delta["content"]
        text = first.get("text")
        return text if isinstance(text, str) else None


def normalize_provider_response(response: Any) -> NormalizedProviderResponse:
    return ProviderResponseNormalizer().normalize(response)
