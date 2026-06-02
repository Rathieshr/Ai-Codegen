"""Azure AI Foundry Phi refinement provider."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


_DEPLOYMENT_METRICS: dict[str, dict[str, Any]] = {}


class AzurePhiProvider:
    """Minimal Azure AI Foundry chat-completions client for strict JSON refinement."""

    def __init__(self) -> None:
        self.enabled = os.getenv("AI_GEN_REFINER_ENABLED") == "1"
        self.endpoint = (os.getenv("AI_GEN_REFINER_ENDPOINT") or "").strip().rstrip("/")
        self.api_key = (os.getenv("AI_GEN_REFINER_API_KEY") or "").strip()
        self.model = (os.getenv("AI_GEN_REFINER_MODEL") or "Phi-4-mini-instruct").strip()
        self.deployment = (os.getenv("AI_GEN_REFINER_DEPLOYMENT") or self.model).strip()
        self.api_version = (os.getenv("AI_GEN_REFINER_API_VERSION") or "2024-05-01-preview").strip()
        self.timeout = _int_env("AI_GEN_REFINER_TIMEOUT_SECONDS", 60)
        self.ping_timeout = _int_env("AI_GEN_REFINER_PING_TIMEOUT_SECONDS", 60)
        self.diagnostic_timeout = _int_env("AI_GEN_REFINER_DIAGNOSTIC_TIMEOUT_SECONDS", 180)
        self.default_max_tokens = _int_env("AI_GEN_REFINER_MAX_TOKENS", 300)
        include_model_env = os.getenv("AI_GEN_REFINER_INCLUDE_MODEL_FIELD")
        if include_model_env is None or not include_model_env.strip():
            self.include_model_field = self._default_include_model_field()
        else:
            self.include_model_field = include_model_env.strip().lower() not in {"0", "false", "no"}
        self.response_format_enabled = os.getenv("AI_GEN_REFINER_RESPONSE_FORMAT_ENABLED", "1") != "0"

    def is_enabled(self) -> bool:
        return bool(self.enabled and self.endpoint and self.api_key and self.model)

    def health_snapshot(self) -> dict[str, Any]:
        metrics = self._deployment_metrics()
        return {
            "deployment": self.deployment,
            "health": self._deployment_health(metrics["consecutive_failures"]),
            "last_success": metrics["last_success_timestamp"],
            "last_failure": metrics["last_failure_timestamp"],
            "average_latency_ms": metrics["average_latency_ms"],
            "consecutive_failures": metrics["consecutive_failures"],
            "provider_used": "azure_phi",
        }

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
        response_format_enabled: bool | None = None,
        allow_retry_without_response_format: bool = True,
        include_model_field: bool | None = None,
        api_version_override: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return self._empty_result("missing_config", "Provider is not fully configured.")

        request_timeout = max(1, int(timeout_seconds)) if timeout_seconds is not None else self.timeout
        effective_max_tokens = max(1, int(max_tokens or self.default_max_tokens))
        use_response_format = self.response_format_enabled if response_format_enabled is None else bool(response_format_enabled)

        attempts: list[dict[str, Any]] = []
        first_attempt = self._attempt_request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=effective_max_tokens,
            timeout_seconds=request_timeout,
            include_response_format=use_response_format,
            attempt_number=1,
            include_model_field=include_model_field,
            api_version_override=api_version_override,
        )
        attempts.append(first_attempt)

        final_attempt = first_attempt
        retried = False
        if use_response_format and allow_retry_without_response_format and self._should_retry_without_response_format(first_attempt):
            retried = True
            retry_attempt = self._attempt_request(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=effective_max_tokens,
                timeout_seconds=request_timeout,
                include_response_format=False,
                attempt_number=2,
                include_model_field=include_model_field,
                api_version_override=api_version_override,
            )
            attempts.append(retry_attempt)
            final_attempt = retry_attempt

        summary = {
            **self.status_snapshot(),
            **self.health_snapshot(),
            "configured": True,
            "http_status": final_attempt.get("http_status"),
            "status": final_attempt.get("status"),
            "raw_content": final_attempt.get("raw_content", ""),
            "raw_response_preview": final_attempt.get("raw_response_preview", ""),
            "parsed_json": final_attempt.get("parsed_json", {}),
            "parse_error": final_attempt.get("parse_error", ""),
            "elapsed_ms": int(final_attempt.get("elapsed_ms") or 0),
            "timeout_seconds": int(final_attempt.get("timeout_seconds") or request_timeout),
            "attempted_url_preview": final_attempt.get("url_preview", ""),
            "attempted_method": final_attempt.get("method", "POST"),
            "include_model_field": self._resolve_include_model_field(include_model_field),
            "api_version": api_version_override or self.api_version,
            "max_tokens": int(final_attempt.get("max_tokens") or effective_max_tokens),
            "response_format_enabled": bool(final_attempt.get("response_format_enabled")),
            "json_mode_attempted": bool(use_response_format),
            "json_mode_retry_without_response_format": retried,
            "failure_reason": final_attempt.get("failure_reason", ""),
            "failure_message": final_attempt.get("failure_message", ""),
            "attempts": attempts,
        }
        return summary

    def safe_config(self) -> dict[str, Any]:
        status = self.status_snapshot()
        return {
            "enabled": self.enabled,
            "provider": "azure_phi",
            "configured": self.is_enabled(),
            "deployment": self.deployment,
            "deployment_health": self.health_snapshot()["health"],
            "endpoint_host": status["endpoint_host"],
            "endpoint_path": status["endpoint_path"],
            "model": self.model or None,
            "api_version": self.api_version,
            "timeout_seconds": self.timeout,
            "ping_timeout_seconds": self.ping_timeout,
            "diagnostic_timeout_seconds": max(self.diagnostic_timeout, self.timeout + 1),
            "include_model_field": self.include_model_field,
            "response_format_enabled": self.response_format_enabled,
            "missing_env": self._missing_env(),
        }

    def debug_curl(self, mode: str = "ping") -> str:
        system_prompt, user_prompt, max_tokens = self.debug_mode_prompt(mode)
        payload = self._build_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            include_response_format=False,
        )
        return (
            f"curl -X POST '{self.final_url()}' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -H 'api-key: <REDACTED>' \\\n"
            f"  -d '{json.dumps(payload, ensure_ascii=True)}'"
        )

    def debug_mode_prompt(self, mode: str) -> tuple[str, str, int]:
        normalized = (mode or "ping").strip().lower()
        if normalized == "small_refine":
            return (
                "Return JSON only.",
                'Return JSON with: {"domain":"","features":[]}\nInput: WhatsApp Hotel Booking Platform',
                300,
            )
        return (
            "Return JSON only.",
            'Return exactly {"status":"ok"}',
            50,
        )

    def status_snapshot(self) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(self.endpoint if "://" in self.endpoint else f"https://{self.endpoint or 'invalid'}")
        final_url = self.final_url()
        final_parsed = urllib.parse.urlparse(final_url) if final_url else urllib.parse.ParseResult("", "", "", "", "", "")
        endpoint_host = parsed.netloc or parsed.path
        endpoint_path = parsed.path or "/"
        return {
            "backend_status": "ok",
            "provider": "azure_phi",
            "configured": self.is_enabled(),
            "enabled": self.enabled,
            "deployment": self.deployment,
            "deployment_health": self.health_snapshot()["health"],
            "endpoint_present": bool(self.endpoint),
            "api_key_present": bool(self.api_key),
            "model": self.model or None,
            "api_version": self.api_version,
            "endpoint_host": endpoint_host,
            "endpoint_path": endpoint_path,
            "final_url_preview": final_url,
            "method": "POST",
            "timeout_seconds": self.timeout,
            "ping_timeout_seconds": self.ping_timeout,
            "diagnostic_timeout_seconds": max(self.diagnostic_timeout, self.timeout + 1),
            "include_model_field": self.include_model_field,
            "max_tokens": self.default_max_tokens,
            "response_format_enabled": self.response_format_enabled,
            "missing_env": self._missing_env(),
            "final_url_host": final_parsed.netloc,
            "final_url_path": final_parsed.path,
        }

    def final_url(self, api_version_override: str | None = None) -> str:
        if not self.endpoint:
            return ""
        parsed = urllib.parse.urlparse(self.endpoint if "://" in self.endpoint else f"https://{self.endpoint}")
        base = f"{parsed.scheme or 'https'}://{parsed.netloc}" if parsed.netloc else self.endpoint
        normalized_path = self._normalize_endpoint_path(parsed.path or "/")
        api_version = (api_version_override or self.api_version).strip() or self.api_version
        return f"{base}{normalized_path}?api-version={urllib.parse.quote(api_version, safe='')}"

    def _normalize_endpoint_path(self, raw_path: str) -> str:
        path = "/" + "/".join(part for part in (raw_path or "/").split("/") if part)
        if path in {"", "/"}:
            return "/models/chat/completions"
        if path == "/models":
            return "/models/chat/completions"
        if path == "/models/chat/completions":
            return path
        if path.endswith("/models/chat/completions"):
            return path
        if path.endswith("/models"):
            return f"{path}/chat/completions"
        if path.endswith("/chat/completions"):
            if "/models/" in f"{path}/" or path.startswith("/models/"):
                return path
            return "/models/chat/completions"
        if "/models" in path.split("/"):
            parts = [part for part in path.split("/") if part]
            model_index = parts.index("models")
            trimmed = "/" + "/".join(parts[: model_index + 1])
            return f"{trimmed}/chat/completions"
        return f"{path}/models/chat/completions"

    def _build_payload(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        include_response_format: bool,
        include_model_field: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if self._resolve_include_model_field(include_model_field):
            payload["model"] = self.deployment or self.model
        if include_response_format:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _attempt_request(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        timeout_seconds: int,
        include_response_format: bool,
        attempt_number: int,
        include_model_field: bool | None = None,
        api_version_override: str | None = None,
    ) -> dict[str, Any]:
        url = self.final_url(api_version_override=api_version_override)
        payload = self._build_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            include_response_format=include_response_format,
            include_model_field=include_model_field,
        )
        started = time.time()
        try:
            print(
                "ai-gen phi probe configured=yes "
                f"attempt={attempt_number} timeout_seconds={timeout_seconds} max_tokens={max_tokens} response_format_enabled={include_response_format} deployment={self.deployment}"
            )
            return self._perform_http_request(
                url=url,
                payload=payload,
                timeout_seconds=timeout_seconds,
                include_response_format=include_response_format,
                attempt_number=attempt_number,
                started=started,
                max_tokens=max_tokens,
            )
        except urllib.error.HTTPError as error:
            body_preview = ""
            try:
                body_preview = error.read().decode("utf-8")
            except Exception:
                body_preview = ""
            return self._error_attempt(
                attempt_number=attempt_number,
                url=url,
                include_response_format=include_response_format,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                started=started,
                http_status=getattr(error, "code", None),
                raw_preview=body_preview[:1500],
                error_type=type(error).__name__,
                error_message=str(error),
            )
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as error:
            return self._error_attempt(
                attempt_number=attempt_number,
                url=url,
                include_response_format=include_response_format,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                started=started,
                http_status=None,
                raw_preview="",
                error_type=type(error).__name__,
                error_message=str(error),
            )

    def raw_http_test(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 50,
        timeout_seconds: int | None = None,
        include_model_field: bool | None = None,
        api_version_override: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return {
                **self.status_snapshot(),
                "configured": False,
                "http_status": None,
                "response_headers": {},
                "response_body_preview": "",
                "elapsed_ms": 0,
                "timeout_seconds": int(timeout_seconds or self.timeout),
                "include_model_field": self._resolve_include_model_field(include_model_field),
                "api_version": api_version_override or self.api_version,
                "final_url_preview": self.final_url(api_version_override=api_version_override),
                "failure_reason": "missing_config",
                "failure_message": "Provider is not fully configured.",
            }

        request_timeout = max(1, int(timeout_seconds)) if timeout_seconds is not None else self.timeout
        payload = self._build_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max(1, int(max_tokens)),
            include_response_format=False,
            include_model_field=include_model_field,
        )
        url = self.final_url(api_version_override=api_version_override)
        started = time.time()
        try:
            result = self._perform_raw_http(
                url=url,
                payload=payload,
                timeout_seconds=request_timeout,
                started=started,
            )
        except urllib.error.HTTPError as error:
            body_preview = ""
            headers = {}
            try:
                body_preview = error.read().decode("utf-8")
            except Exception:
                body_preview = ""
            try:
                headers = dict(error.headers.items())
            except Exception:
                headers = {}
            elapsed_ms = int((time.time() - started) * 1000)
            failure_reason = self._classify_failure(getattr(error, "code", None), type(error).__name__, url)
            return {
                **self.status_snapshot(),
                "http_status": getattr(error, "code", None),
                "response_headers": headers,
                "response_body_preview": body_preview[:1500],
                "elapsed_ms": elapsed_ms,
                "timeout_seconds": request_timeout,
                "include_model_field": self._resolve_include_model_field(include_model_field),
                "api_version": api_version_override or self.api_version,
                "final_url_preview": url,
                "failure_reason": failure_reason,
                "failure_message": self._failure_message(failure_reason),
                "error_type": type(error).__name__,
                "error_message": str(error)[:500],
            }
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as error:
            elapsed_ms = int((time.time() - started) * 1000)
            failure_reason = self._classify_failure(None, type(error).__name__, url)
            return {
                **self.status_snapshot(),
                "http_status": None,
                "response_headers": {},
                "response_body_preview": "",
                "elapsed_ms": elapsed_ms,
                "timeout_seconds": request_timeout,
                "include_model_field": self._resolve_include_model_field(include_model_field),
                "api_version": api_version_override or self.api_version,
                "final_url_preview": url,
                "failure_reason": failure_reason,
                "failure_message": self._failure_message(failure_reason),
                "error_type": type(error).__name__,
                "error_message": str(error)[:500],
            }

        return {
            **self.status_snapshot(),
            "http_status": result["http_status"],
            "response_headers": result["response_headers"],
            "response_body_preview": result["response_body_preview"],
            "elapsed_ms": result["elapsed_ms"],
            "timeout_seconds": request_timeout,
            "include_model_field": self._resolve_include_model_field(include_model_field),
            "api_version": api_version_override or self.api_version,
            "final_url_preview": url,
            "failure_reason": "",
            "failure_message": "",
            "error_type": "",
            "error_message": "",
        }

    def _parse_success_response(
        self,
        attempt_number: int,
        url: str,
        include_response_format: bool,
        timeout_seconds: int,
        max_tokens: int,
        http_status: int,
        response_body: str,
        elapsed_ms: int,
    ) -> dict[str, Any]:
        try:
            raw = json.loads(response_body)
            content = raw["choices"][0]["message"]["content"]
            parsed_json = json.loads(_normalize_json_content(content))
            if not isinstance(parsed_json, dict):
                return self._structured_attempt(
                    attempt_number=attempt_number,
                    url=url,
                    include_response_format=include_response_format,
                    timeout_seconds=timeout_seconds,
                    max_tokens=max_tokens,
                    http_status=http_status,
                    status="parse_error",
                    raw_content=content,
                    parsed_json={},
                    parse_error="NonDictParsedJson",
                    elapsed_ms=elapsed_ms,
                    failure_reason="parse_error",
                    failure_message="Model returned JSON that was not an object.",
                    error_type="NonDictParsedJson",
                    error_message="Model returned JSON that was not an object.",
                )
            print("ai-gen phi probe parse_result=dict validation_candidate=yes")
            self._record_success(elapsed_ms)
            return self._structured_attempt(
                attempt_number=attempt_number,
                url=url,
                include_response_format=include_response_format,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                http_status=http_status,
                status="success",
                raw_content=content,
                parsed_json=parsed_json,
                parse_error="",
                elapsed_ms=elapsed_ms,
                failure_reason="",
                failure_message="",
                error_type="",
                error_message="",
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            print(f"ai-gen phi probe parse_result=error validation_candidate=no error={type(error).__name__}")
            self._record_failure(elapsed_ms)
            return self._structured_attempt(
                attempt_number=attempt_number,
                url=url,
                include_response_format=include_response_format,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                http_status=http_status,
                status="parse_error",
                raw_content=response_body[:4000],
                parsed_json={},
                parse_error=type(error).__name__,
                elapsed_ms=elapsed_ms,
                failure_reason="parse_error",
                failure_message="Model response could not be parsed into the expected chat-completions JSON shape.",
                error_type=type(error).__name__,
                error_message=str(error),
            )

    def _error_attempt(
        self,
        attempt_number: int,
        url: str,
        include_response_format: bool,
        timeout_seconds: int,
        max_tokens: int,
        started: float,
        http_status: int | None,
        raw_preview: str,
        error_type: str,
        error_message: str,
    ) -> dict[str, Any]:
        elapsed_ms = int((time.time() - started) * 1000)
        failure_reason = self._classify_failure(http_status, error_type, url)
        failure_message = self._failure_message(failure_reason)
        self._record_failure(elapsed_ms)
        status = "timeout" if failure_reason in {"timeout", "provider_timeout"} else "error"
        print(
            "ai-gen phi probe "
            f"http_status={http_status or 'error'} error={error_type} elapsed_ms={elapsed_ms} failure_reason={failure_reason} deployment={self.deployment}"
        )
        return self._structured_attempt(
            attempt_number=attempt_number,
            url=url,
            include_response_format=include_response_format,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            http_status=http_status,
            status=status,
            raw_content=raw_preview,
            parsed_json={},
            parse_error=error_type,
            elapsed_ms=elapsed_ms,
            failure_reason=failure_reason,
            failure_message=failure_message,
            error_type=error_type,
            error_message=error_message[:500],
        )

    def _structured_attempt(
        self,
        attempt_number: int,
        url: str,
        include_response_format: bool,
        timeout_seconds: int,
        max_tokens: int,
        http_status: int | None,
        status: str,
        raw_content: str,
        parsed_json: dict[str, Any],
        parse_error: str,
        elapsed_ms: int,
        failure_reason: str,
        failure_message: str,
        error_type: str,
        error_message: str,
    ) -> dict[str, Any]:
        return {
            "attempt_number": attempt_number,
            "url_preview": url,
            "method": "POST",
            "response_format_enabled": include_response_format,
            "http_status": http_status,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "timeout_seconds": timeout_seconds,
            "raw_response_preview": raw_content[:1500],
            "raw_content": raw_content,
            "parsed_json": parsed_json,
            "parse_error": parse_error,
            "max_tokens": max_tokens,
            "error_type": error_type,
            "error_message": error_message,
            "failure_reason": failure_reason,
            "failure_message": failure_message,
        }

    def _perform_http_request(
        self,
        url: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        include_response_format: bool,
        attempt_number: int,
        started: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        raw_result = self._perform_raw_http(
            url=url,
            payload=payload,
            timeout_seconds=timeout_seconds,
            started=started,
        )
        print(
            "ai-gen phi probe "
            f"http_status={raw_result['http_status']} response_length={raw_result['response_length']} elapsed_ms={raw_result['elapsed_ms']}"
        )
        return self._parse_success_response(
            attempt_number=attempt_number,
            url=url,
            include_response_format=include_response_format,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            http_status=raw_result["http_status"],
            response_body=raw_result["response_body"],
            elapsed_ms=raw_result["elapsed_ms"],
        )

    def _perform_raw_http(
        self,
        url: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        started: float,
    ) -> dict[str, Any]:
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
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            http_status = getattr(response, "status", 200)
            response_body = response.read().decode("utf-8")
            elapsed_ms = int((time.time() - started) * 1000)
            try:
                headers = dict(response.headers.items())
            except Exception:
                headers = {}
            return {
                "http_status": http_status,
                "response_headers": headers,
                "response_body": response_body,
                "response_body_preview": response_body[:1500],
                "response_length": len(response_body),
                "elapsed_ms": elapsed_ms,
            }

    def _classify_failure(self, http_status: int | None, error_type: str, url: str) -> str:
        if not self.enabled or not self.endpoint or not self.api_key or not self.model:
            return "missing_config"
        if "/models/chat/completions" not in url:
            return "wrong_endpoint_path"
        normalized_error = (error_type or "").lower()
        if normalized_error in {"timeouterror", "timeout", "sockettimeout"}:
            return "provider_timeout"
        if normalized_error in {"urlerror", "oserror"}:
            return "connection_error"
        if http_status == 401:
            return "http_401_invalid_key"
        if http_status == 403:
            return "http_403_forbidden"
        if http_status == 404:
            return "http_404_wrong_endpoint_or_model"
        if http_status == 405:
            return "http_405_wrong_method_or_path"
        if http_status == 429:
            return "http_429_rate_limited"
        return "parse_error"

    def _failure_message(self, failure_reason: str) -> str:
        messages = {
            "missing_config": "Azure Phi is not fully configured in the backend environment.",
            "wrong_endpoint_path": "Configured endpoint path is missing /models/chat/completions.",
            "provider_timeout": "Azure Phi request timed out before returning a response.",
            "http_401_invalid_key": "Azure Phi rejected the API key.",
            "http_403_forbidden": "Azure Phi access is forbidden for this endpoint or model.",
            "http_404_wrong_endpoint_or_model": "Azure Phi endpoint or model path was not found.",
            "http_405_wrong_method_or_path": "Azure Phi endpoint rejected the HTTP method or path.",
            "http_429_rate_limited": "Azure Phi request was rate limited.",
            "connection_error": "Azure Phi endpoint could not be reached from the backend.",
            "parse_error": "Azure Phi returned a response that could not be parsed.",
        }
        return messages.get(failure_reason, "Azure Phi request failed.")

    def _should_retry_without_response_format(self, result: dict[str, Any]) -> bool:
        return str(result.get("failure_reason") or "") in {
            "provider_timeout",
            "http_404_wrong_endpoint_or_model",
            "http_405_wrong_method_or_path",
            "parse_error",
        }

    def _missing_env(self) -> list[str]:
        missing: list[str] = []
        if not self.enabled:
            missing.append("AI_GEN_REFINER_ENABLED")
        if not self.endpoint:
            missing.append("AI_GEN_REFINER_ENDPOINT")
        if not self.api_key:
            missing.append("AI_GEN_REFINER_API_KEY")
        if not self.model:
            missing.append("AI_GEN_REFINER_MODEL")
        return missing

    def _empty_result(self, failure_reason: str, failure_message: str) -> dict[str, Any]:
        return {
            **self.status_snapshot(),
            "configured": False,
            "http_status": None,
            "status": "error",
            "raw_content": "",
            "raw_response_preview": "",
            "parsed_json": {},
            "parse_error": failure_reason,
            "elapsed_ms": 0,
            "timeout_seconds": self.timeout,
            "attempted_url_preview": self.final_url(),
            "attempted_method": "POST",
            "max_tokens": self.default_max_tokens,
            "response_format_enabled": self.response_format_enabled,
            "json_mode_attempted": False,
            "json_mode_retry_without_response_format": False,
            "failure_reason": failure_reason,
            "failure_message": failure_message,
            "attempts": [],
        }

    def _resolve_include_model_field(self, include_model_field: bool | None) -> bool:
        if include_model_field is None:
            return self.include_model_field
        return bool(include_model_field)

    def _default_include_model_field(self) -> bool:
        if not self.endpoint:
            return True
        parsed = urllib.parse.urlparse(self.endpoint if "://" in self.endpoint else f"https://{self.endpoint}")
        host = (parsed.netloc or parsed.path or "").lower()
        path = self._normalize_endpoint_path(parsed.path or "/")
        if host.endswith(".services.ai.azure.com") and path.startswith("/models/chat/completions"):
            return False
        return True

    def _deployment_metrics(self) -> dict[str, Any]:
        metrics = _DEPLOYMENT_METRICS.get(self.deployment)
        if metrics is None:
            metrics = {
                "deployment_name": self.deployment,
                "last_success_timestamp": None,
                "last_failure_timestamp": None,
                "consecutive_failures": 0,
                "average_latency_ms": 0,
                "success_count": 0,
            }
            _DEPLOYMENT_METRICS[self.deployment] = metrics
        return metrics

    def _record_success(self, elapsed_ms: int) -> None:
        metrics = self._deployment_metrics()
        metrics["last_success_timestamp"] = _utc_now()
        metrics["consecutive_failures"] = 0
        metrics["success_count"] = int(metrics.get("success_count") or 0) + 1
        previous_average = int(metrics.get("average_latency_ms") or 0)
        count = metrics["success_count"]
        metrics["average_latency_ms"] = int(((previous_average * (count - 1)) + max(0, elapsed_ms)) / count)

    def _record_failure(self, elapsed_ms: int) -> None:
        metrics = self._deployment_metrics()
        metrics["last_failure_timestamp"] = _utc_now()
        metrics["consecutive_failures"] = int(metrics.get("consecutive_failures") or 0) + 1
        if not metrics.get("average_latency_ms"):
            metrics["average_latency_ms"] = max(0, elapsed_ms)

    def _deployment_health(self, consecutive_failures: int) -> str:
        if consecutive_failures >= 5:
            return "unhealthy"
        if consecutive_failures >= 3:
            return "degraded"
        return "healthy"


def _normalize_json_content(content: Any) -> str:
    if not isinstance(content, str):
        return json.dumps(content)
    normalized = content.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines:
            lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
    return normalized


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
