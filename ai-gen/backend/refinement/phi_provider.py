"""Azure AI Foundry Phi refinement provider."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class AzurePhiProvider:
    """Minimal Azure AI Foundry chat-completions client for strict JSON refinement."""

    def __init__(self) -> None:
        self.endpoint = (os.getenv("AI_GEN_REFINER_ENDPOINT") or "").strip().rstrip("/")
        self.api_key = (os.getenv("AI_GEN_REFINER_API_KEY") or "").strip()
        self.model = (os.getenv("AI_GEN_REFINER_MODEL") or "Phi-4-mini-instruct").strip()
        self.api_version = (os.getenv("AI_GEN_REFINER_API_VERSION") or "2024-05-01-preview").strip()
        try:
            self.timeout = max(1, int(os.getenv("AI_GEN_REFINER_TIMEOUT_SECONDS", "20")))
        except ValueError:
            self.timeout = 20

    def is_enabled(self) -> bool:
        return bool(
            os.getenv("AI_GEN_REFINER_ENABLED") == "1"
            and self.endpoint
            and self.api_key
            and self.model
        )

    def refine_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 800) -> dict[str, Any]:
        if not self.is_enabled():
            return {}

        url = f"{self.endpoint}/chat/completions?api-version={self.api_version}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            print(f"ai-gen refiner error: {type(error).__name__}")
            return {}

        try:
            content = raw["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except (KeyError, IndexError, TypeError, ValueError):
            return {}
