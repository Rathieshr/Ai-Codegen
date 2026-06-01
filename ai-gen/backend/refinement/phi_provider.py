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
        result = self.probe_json(system_prompt, user_prompt, max_tokens=max_tokens)
        parsed = result.get("parsed_json")
        return parsed if isinstance(parsed, dict) else {}

    def probe_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 800,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_enabled():
            print("ai-gen phi probe configured=no")
            return {"configured": False, "http_status": None, "raw_content": "", "parsed_json": {}, "parse_error": "provider not enabled"}

        request_timeout = max(1, int(timeout_seconds)) if timeout_seconds is not None else self.timeout
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
            print(f"ai-gen phi probe configured=yes timeout_seconds={request_timeout}")
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                status_code = getattr(response, "status", 200)
                response_body = response.read().decode("utf-8")
                print(f"ai-gen phi probe configured=yes http_status={status_code} response_length={len(response_body)}")
                raw = json.loads(response_body)
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            http_status = getattr(error, "code", None)
            print(f"ai-gen phi probe configured=yes http_status={http_status or 'error'} error={type(error).__name__}")
            return {
                "configured": True,
                "http_status": http_status,
                "raw_content": "",
                "parsed_json": {},
                "parse_error": type(error).__name__,
            }

        try:
            content = raw["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            is_valid = isinstance(parsed, dict)
            print(f"ai-gen phi probe parse_result={'dict' if is_valid else 'non_dict'} validation_candidate={'yes' if is_valid else 'no'}")
            return {
                "configured": True,
                "http_status": status_code,
                "raw_content": content,
                "parsed_json": parsed if is_valid else {},
                "parse_error": "",
            }
        except (KeyError, IndexError, TypeError, ValueError) as error:
            print(f"ai-gen phi probe parse_result=error validation_candidate=no error={type(error).__name__}")
            return {
                "configured": True,
                "http_status": 200,
                "raw_content": str(raw)[:4000],
                "parsed_json": {},
                "parse_error": type(error).__name__,
            }
