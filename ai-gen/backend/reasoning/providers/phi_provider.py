"""Azure Phi adapter for the provider-neutral Reasoning Layer."""

from __future__ import annotations

import os
from typing import Any

from ..models import ReasoningRequest


class PhiProvider:
    name = "Phi"

    def __init__(self, provider: Any = None, model: str = "") -> None:
        self._provider = provider
        self.model = model or os.getenv("AI_GEN_REFINER_MODEL", "")

    def _resolve(self) -> Any:
        if self._provider is None:
            from backend.refinement.provider import get_refinement_provider

            self._provider = get_refinement_provider()
        return self._provider

    def is_available(self) -> bool:
        provider = self._resolve()
        return bool(provider and provider.is_enabled())

    def analyze(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute(prompt, request)

    def recommend(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute(prompt, request)

    def summarize(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute(prompt, request)

    def refine(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute(prompt, request)

    def reason(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute(prompt, request)

    def _execute(self, prompt: str, request: ReasoningRequest) -> Any:
        provider = self._resolve()
        if not provider or not provider.is_enabled():
            raise RuntimeError("Phi reasoning provider is not configured.")
        probe = provider.probe_json(
            "Return only the requested JSON object. Use only supplied evidence.",
            prompt,
            max_tokens=_output_token_limit(request),
        )
        parsed = probe.get("parsed_json")
        if isinstance(parsed, dict) and parsed:
            return {
                "content": parsed,
                "_reasoning_metadata": {
                    "promptTokens": int(probe.get("prompt_tokens") or 0),
                    "completionTokens": int(probe.get("completion_tokens") or 0),
                    "latencyMs": int(probe.get("elapsed_ms") or 0),
                    "finishReason": probe.get("finish_reason") or "",
                },
            }
        raw = probe.get("raw_content") or probe.get("raw_provider_response")
        if raw:
            return {
                "content": raw,
                "_reasoning_metadata": {
                    "promptTokens": int(probe.get("prompt_tokens") or 0),
                    "completionTokens": int(probe.get("completion_tokens") or 0),
                    "latencyMs": int(probe.get("elapsed_ms") or 0),
                },
            }
        raise RuntimeError(probe.get("failure_message") or "Phi returned no reasoning response.")


def _output_token_limit(request: ReasoningRequest) -> int:
    configured = int(
        os.getenv(
            "HEI_REASONING_MAX_OUTPUT_TOKENS",
            os.getenv("AI_GEN_REFINER_MAX_TOKENS", "300"),
        )
    )
    requested = int(request.options.get("_maxOutputTokens") or configured)
    return max(1, min(configured, requested))
